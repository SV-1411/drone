"""Bench-only ESP32 sound-alert receiver for the drone Raspberry Pi.

The service accepts authenticated node alerts, checks their fixed surveyed
location, and records them. It deliberately has no arming/takeoff path: a
KY-037 loudness trigger is not a verified distress classifier.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MAX_BODY = 2048


def load_nodes(path: Path) -> dict[str, tuple[float, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("node registry must be an object")
    nodes: dict[str, tuple[float, float]] = {}
    for node_id, coords in data.items():
        if not isinstance(node_id, str) or not isinstance(coords, dict):
            raise ValueError("invalid node registry entry")
        lat, lon = float(coords["lat"]), float(coords["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"invalid coordinates for {node_id}")
        nodes[node_id] = (lat, lon)
    return nodes


def validate_alert(body: bytes, signature: str, key: bytes,
                   nodes: dict[str, tuple[float, float]],
                   previous: dict[str, int]) -> dict:
    if len(body) > MAX_BODY:
        raise ValueError("body too large")
    if len(signature) != 64:
        raise PermissionError("missing or malformed signature")
    expected = hmac.new(key, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise PermissionError("invalid signature")
    try:
        event = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(event, dict):
        raise ValueError("alert must be an object")
    node_id = event.get("node_id")
    if node_id not in nodes:
        raise ValueError("unknown node")
    if event.get("kind") != "sound_level_candidate":
        raise ValueError("unsupported alert kind")
    seq = event.get("seq")
    if type(seq) is not int or seq < 1 or seq <= previous.get(node_id, 0):
        raise ValueError("duplicate or stale sequence")
    lat, lon = nodes[node_id]
    try:
        supplied_lat, supplied_lon = float(event["lat"]), float(event["lon"])
        sound_score = float(event["sound_score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("missing or invalid alert values") from exc
    if abs(supplied_lat - lat) > 0.00001 or abs(supplied_lon - lon) > 0.00001:
        raise ValueError("node coordinates do not match registry")
    if not 0 <= sound_score <= 1:
        raise ValueError("invalid sound score")
    return {"node_id": node_id, "seq": seq, "lat": lat, "lon": lon,
            "sound_score": sound_score, "kind": "sound_level_candidate"}


class AlertServer(ThreadingHTTPServer):
    def __init__(self, address, key: bytes, nodes: dict[str, tuple[float, float]],
                 database: Path):
        super().__init__(address, AlertHandler)
        self.key, self.nodes = key, nodes
        self.database = database
        self.previous: dict[str, int] = {}
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TABLE IF NOT EXISTS alerts (node_id TEXT NOT NULL, seq INTEGER NOT NULL, received_at REAL NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, sound_score REAL NOT NULL, PRIMARY KEY(node_id, seq))")
            for node_id, seq in db.execute("SELECT node_id, MAX(seq) FROM alerts GROUP BY node_id"):
                self.previous[node_id] = seq


class AlertHandler(BaseHTTPRequestHandler):
    server: AlertServer

    def _reply(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._reply(200, {"ok": True, "nodes_configured": len(self.server.nodes),
                              "dispatch": "LOCKED_BENCH_ONLY"})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/alert":
            self._reply(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reply(400, {"error": "invalid length"})
            return
        if not 0 < size <= MAX_BODY:
            self._reply(413, {"error": "invalid body size"})
            return
        body = self.rfile.read(size)
        try:
            event = validate_alert(body, self.headers.get("X-Alert-Signature", ""),
                                   self.server.key, self.server.nodes,
                                   self.server.previous)
        except PermissionError as exc:
            self._reply(401, {"error": str(exc)})
            return
        except ValueError as exc:
            self._reply(400, {"error": str(exc)})
            return
        try:
            with sqlite3.connect(self.server.database) as db:
                db.execute("INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?)",
                           (event["node_id"], event["seq"], time.time(),
                            event["lat"], event["lon"], event["sound_score"]))
        except sqlite3.IntegrityError:
            self._reply(409, {"error": "duplicate sequence"})
            return
        self.server.previous[event["node_id"]] = event["seq"]
        print(json.dumps({"received": event, "dispatch": "LOCKED_BENCH_ONLY"}), flush=True)
        self._reply(200, {"accepted": True, "dispatch": "LOCKED_BENCH_ONLY"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=Path.home() / "logs" / "wifi_alerts.sqlite3")
    parser.add_argument("--relay-url", default=os.environ.get("VANNI_RELAY_URL", ""),
                        help="HTTPS base URL for the best-effort cloud relay")
    parser.add_argument("--relay-token", default=os.environ.get("VANNI_RELAY_PI_TOKEN", ""),
                        help="Pi-only bearer token; provide through a protected environment file")
    parser.add_argument("--init", action="store_true", help="create a private key file and empty registry, then exit")
    parser.add_argument("--set-node", nargs=3, metavar=("ID", "LAT", "LON"),
                        help="record the surveyed fixed location, then exit")
    args = parser.parse_args()
    if args.init:
        config_dir = Path.home() / ".config" / "vannikawachh"
        config_dir.mkdir(parents=True, exist_ok=True)
        env_file = config_dir / "wifi-alert.env"
        if not env_file.exists():
            with env_file.open("x", encoding="ascii") as output:
                output.write("VANNI_ALERT_KEY=" + secrets.token_hex(32) + "\n")
            env_file.chmod(0o600)
        if not args.registry.exists():
            args.registry.write_text("{}\n", encoding="utf-8")
        print(f"Config prepared: {env_file}, {args.registry}; key not printed")
        return
    if args.set_node:
        node_id, raw_lat, raw_lon = args.set_node
        if not node_id or any(not (ch.isalnum() or ch == "-") for ch in node_id):
            parser.error("node ID must contain only letters, numbers, or hyphens")
        lat, lon = float(raw_lat), float(raw_lon)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            parser.error("invalid node coordinates")
        nodes = json.loads(args.registry.read_text(encoding="utf-8"))
        nodes[node_id] = {"lat": lat, "lon": lon}
        args.registry.write_text(json.dumps(nodes, indent=2) + "\n", encoding="utf-8")
        print(f"Fixed configured location stored for {node_id}; restart receiver to load it")
        return
    key_hex = os.environ.get("VANNI_ALERT_KEY", "")
    if len(key_hex) != 64:
        parser.error("VANNI_ALERT_KEY must be a 32-byte hex key")
    key = bytes.fromhex(key_hex)
    with AlertServer((args.host, args.port), key, load_nodes(args.registry), args.database) as server:
        print(f"Listening on {args.host}:{args.port}; dispatch LOCKED_BENCH_ONLY", flush=True)
        relay_stop = threading.Event()
        relay_thread = None
        if args.relay_url and args.relay_token:
            relay_thread = threading.Thread(target=cloud_relay_loop,
                args=(server, args.relay_url.rstrip("/"), args.relay_token, relay_stop), daemon=True)
            relay_thread.start()
            print("Cloud relay polling enabled; flight dispatch remains locked", flush=True)
        server.serve_forever()
        relay_stop.set()
        if relay_thread:
            relay_thread.join(timeout=3)


def cloud_relay_loop(server: AlertServer, relay_url: str, token: str,
                     stop: threading.Event) -> None:
    """Poll the cloud queue, persist to the local Pi, then acknowledge it."""
    headers = {"Authorization": "Bearer " + token}
    while not stop.is_set():
        try:
            req = Request(relay_url + "/edge/pending?limit=20", headers=headers)
            with urlopen(req, timeout=8) as response:
                events = json.load(response).get("events", [])
            for item in events:
                try:
                    body = base64.b64decode(item["body_b64"], validate=True)
                    signature = item["signature"]
                    identity = json.loads(body)
                    node_id, seq = identity["node_id"], identity["seq"]
                    with sqlite3.connect(server.database) as db:
                        found = db.execute("SELECT 1 FROM alerts WHERE node_id=? AND seq=?",
                                           (node_id, seq)).fetchone()
                    if not found:
                        post = Request(f"http://127.0.0.1:{server.server_port}/alert", body,
                            headers={"Content-Type": "application/json",
                                     "X-Alert-Signature": signature}, method="POST")
                        with urlopen(post, timeout=5):
                            pass
                    ack_body = json.dumps({"node_id": node_id, "seq": seq}).encode()
                    ack = Request(relay_url + "/edge/ack", ack_body,
                        headers={**headers, "Content-Type": "application/json"}, method="POST")
                    with urlopen(ack, timeout=5):
                        pass
                except (KeyError, TypeError, ValueError, HTTPError, URLError, OSError) as exc:
                    print(f"Cloud alert pending; retrying: {type(exc).__name__}", flush=True)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            print(f"Cloud relay unavailable; local listener remains active: {type(exc).__name__}", flush=True)
        stop.wait(2)


if __name__ == "__main__":
    main()
