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
import sys
import time
import threading
import wave
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from math import asin, cos, isfinite, radians, sin, sqrt


MAX_BODY = 2048
MAX_AUDIO_BYTES = 64_000  # 2 s, 16 kHz, mono, signed 16-bit PCM


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
                 database: Path, relay_url: str = ""):
        super().__init__(address, AlertHandler)
        self.key, self.nodes = key, nodes
        self.relay_url = relay_url.rstrip("/")
        self.database = database
        self.previous: dict[str, int] = {}
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TABLE IF NOT EXISTS alerts (node_id TEXT NOT NULL, seq INTEGER NOT NULL, received_at REAL NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, sound_score REAL NOT NULL, PRIMARY KEY(node_id, seq))")
            db.execute("CREATE TABLE IF NOT EXISTS bench_once (id INTEGER PRIMARY KEY CHECK(id=1), node_id TEXT NOT NULL, seq INTEGER NOT NULL, created REAL NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL)")
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
        if self.path == "/audio":
            self._receive_audio()
            return
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
        # Older ESP firmware sends to the Pi only. Mirror its already-verified
        # signed packet to Render so the live dashboard can show the real node.
        # Skip loopback packets fetched from Render to avoid a relay loop.
        if self.server.relay_url and self.client_address[0] not in ("127.0.0.1", "::1"):
            threading.Thread(target=mirror_to_cloud,
                args=(self.server.relay_url, body,
                      self.headers.get("X-Alert-Signature", "")), daemon=True).start()
        maybe_trigger_one_bench_check(self.server, event)

    def _receive_audio(self) -> None:
        """Attach one authenticated PCM clip to an already accepted alert."""
        node_id = self.headers.get("X-Node-Id", "")
        raw_seq = self.headers.get("X-Alert-Seq", "")
        signature = self.headers.get("X-Audio-Signature", "")
        try:
            size = int(self.headers.get("Content-Length", "0"))
            seq = int(raw_seq)
        except ValueError:
            self._reply(400, {"error": "invalid audio headers"})
            return
        if (size != MAX_AUDIO_BYTES or seq < 1 or node_id not in self.server.nodes
                or not node_id.replace("-", "").isalnum()):
            self._reply(400, {"error": "invalid clip identity or length"})
            return
        if len(signature) != 64:
            self._reply(401, {"error": "audio signature missing"})
            return
        body = self.rfile.read(size)
        if len(body) != size:
            self._reply(400, {"error": "incomplete audio body"})
            return
        prefix = f"{node_id}:{seq}:".encode("ascii")
        expected = hmac.new(self.server.key, prefix + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            self._reply(401, {"error": "invalid audio signature"})
            return
        with sqlite3.connect(self.server.database) as db:
            known = db.execute("SELECT 1 FROM alerts WHERE node_id=? AND seq=?",
                               (node_id, seq)).fetchone()
        if not known:
            self._reply(409, {"error": "matching alert has not arrived"})
            return
        clips_dir = self.server.database.parent / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        path = clips_dir / f"{node_id}-{seq}.wav"
        try:
            with path.open("xb") as output:
                with wave.open(output, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16_000)
                    wav.writeframes(body)
        except FileExistsError:
            self._reply(409, {"error": "clip already received"})
            return
        self._reply(200, {"accepted": True, "node_id": node_id, "seq": seq,
                          "bytes": size, "verification": "pending"})
        threading.Thread(target=verify_audio_clip,
            args=(path, node_id, seq, self.server.relay_url,
                  os.environ.get("VANNI_RELAY_PI_TOKEN", "")), daemon=True).start()


def verify_audio_clip(path: Path, node_id: str, seq: int,
                      relay_url: str, relay_token: str) -> None:
    """Run Stage 2 and report its result; this path never dispatches a flight.

    The receiver is installed in the small flight-service directory on the
    drone Pi, while the audio model package is kept in the main VanniKawachh
    source directory.  Make that deliberately configured source available to
    this worker rather than silently treating an import-path mismatch as a
    failed audio model.
    """
    result = {"node_id": node_id, "seq": seq, "audio_received": True,
              "confirmed": False, "backend": "unavailable", "score": 0.0}
    try:
        stage2_root = os.environ.get(
            "VANNI_STAGE2_ROOT", "/home/vannidrone/vannikawachh"
        )
        if stage2_root not in sys.path:
            sys.path.insert(0, stage2_root)
        from hub.verifier import Stage2Verifier
        # Stage2Verifier selects PANNs first, then the committed learned
        # YAMNet model.  Its explicitly named development fallback remains
        # visible in the report if no learned runtime is installed.
        verifier = Stage2Verifier()
        decision = verifier.verify_wav_detail(str(path), allow_spoken_stress=True)
        result.update(confirmed=bool(decision.distress_confirmed),
                      backend=decision.backend,
                      score=float(decision.classifier_probability))
    except Exception as exc:
        result["error"] = type(exc).__name__
    print(json.dumps({"audio_verification": result}), flush=True)
    if relay_url and relay_token:
        try:
            request = Request(relay_url + "/edge/verification",
                json.dumps(result).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + relay_token}, method="POST")
            with urlopen(request, timeout=8):
                pass
        except (HTTPError, URLError, OSError):
            print(f"Cloud audio result unavailable for {node_id}#{seq}", flush=True)


def maybe_trigger_one_bench_check(server: AlertServer, event: dict) -> None:
    """Use the next authenticated ESP alert for one props-off arm check.

    No model confidence threshold is applied at this point. The SQLite row
    consumes the one-shot across receiver restarts before any motor command.
    """
    if os.environ.get("VANNI_BENCH_NEXT_ALERT", "") != "1":
        return
    if os.environ.get("VANNI_PILOT_READY", "") != "1":
        print("Bench-next-alert requested but pilot flag is absent", flush=True)
        return
    with sqlite3.connect(server.database) as db:
        inserted = db.execute(
            "INSERT OR IGNORE INTO bench_once VALUES (1,?,?,?,?,?)",
            (event["node_id"], event["seq"], time.time(), "claimed", ""),
        ).rowcount
    if inserted != 1:
        return
    threading.Thread(target=_run_one_bench_check,
        args=(server.database, event["node_id"], event["seq"]), daemon=True).start()


def _run_one_bench_check(database: Path, node_id: str, seq: int) -> None:
    api_url = os.environ.get("VANNI_FLIGHT_API_URL", "http://127.0.0.1:8000").rstrip("/")
    api_token = os.environ.get("VANNI_FLIGHT_API_TOKEN", "")
    status, detail = request_props_off_check(api_url, api_token)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE bench_once SET status=?, detail=? WHERE id=1",
                   (status, detail))
    print(json.dumps({"bench_once": {"node_id": node_id, "seq": seq,
                                     "status": status, "detail": detail}}), flush=True)


def mirror_to_cloud(relay_url: str, body: bytes, signature: str) -> None:
    try:
        request = Request(relay_url + "/edge/alert", body,
            headers={"Content-Type": "application/json",
                     "X-Alert-Signature": signature}, method="POST")
        with urlopen(request, timeout=8) as response:
            if response.status != 200:
                print(f"Cloud mirror returned HTTP {response.status}", flush=True)
    except (HTTPError, URLError, OSError) as exc:
        print(f"Cloud mirror unavailable; local alert retained: {type(exc).__name__}", flush=True)


def distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    a, b = radians(a_lat), radians(b_lat)
    c, d = radians(b_lat - a_lat), radians(b_lon - a_lon)
    return 2 * 6_371_000 * asin(sqrt(sin(c / 2) ** 2 +
                                    cos(a) * cos(b) * sin(d / 2) ** 2))


def real_flight_preflight(telemetry: dict, lat: float, lon: float,
                          max_target_m: float,
                          allow_missing_battery: bool = False) -> str | None:
    """Return the reason to refuse dispatch, or None when basic checks pass.

    This complements rather than replaces ArduPilot pre-arm, radio, geofence,
    and the mission executor's flight-time failsafes.
    """
    state = telemetry.get("state")
    # The flight API retains the last mission ID in telemetry after a normal
    # completion. It is historical in COMPLETED, but anomalous in IDLE.
    if (state not in ("IDLE", "COMPLETED") or
            (state == "IDLE" and telemetry.get("mission_id"))):
        return "flight controller is not idle"
    if telemetry.get("armed") is not False:
        return "aircraft is already armed or arm state is unknown"
    if (telemetry.get("gps_fix") or 0) < 3 or (telemetry.get("gps_sats") or 0) < 8:
        return "GPS has no reliable 3D fix"
    battery = telemetry.get("battery_pct")
    voltage = telemetry.get("battery_voltage")
    if battery is not None and battery < 30:
        return "battery is below 30%"
    if not allow_missing_battery and (battery is None or not voltage):
        return "battery telemetry is missing"
    current_lat, current_lon = telemetry.get("lat"), telemetry.get("lon")
    if (current_lat is None or current_lon is None or
            not all(isfinite(float(x)) for x in (current_lat, current_lon, lat, lon)) or
            current_lat == 0 or current_lon == 0):
        return "aircraft location is unavailable"
    if allow_missing_battery:
        home_lat, home_lon = telemetry.get("home_lat"), telemetry.get("home_lon")
        if (home_lat is None or home_lon is None or
                not all(isfinite(float(x)) for x in (home_lat, home_lon)) or
                distance_m(float(current_lat), float(current_lon),
                           float(home_lat), float(home_lon)) > 20):
            return "surveyed home must be within 20 m of the aircraft"
        max_target_m = min(max_target_m, 30.0)
    if distance_m(float(current_lat), float(current_lon), lat, lon) > max_target_m:
        return "target is beyond the locally configured test radius"
    return None


def process_real_test(command: dict, api_url: str, api_token: str,
                      enabled: bool, pilot_ready: bool, max_target_m: float,
                      allow_missing_battery: bool = False) -> tuple[str, str]:
    if command.get("node_id") == "operator-diagnostic":
        # This branch must never call /trigger or a bench/motor endpoint.
        try:
            with urlopen(api_url + "/health", timeout=3) as response:
                health = json.load(response)
            if health.get("vehicle_connected") is not True:
                return "completed", "Pi reached; Pixhawk MAVLink is disconnected"
            with urlopen(api_url + "/telemetry", timeout=3) as response:
                telemetry = json.load(response)
            reason = real_flight_preflight(telemetry, float(command["lat"]),
                                           float(command["lon"]), max_target_m,
                                           allow_missing_battery)
            if not enabled or not pilot_ready or not health.get("flight_limits", {}).get(
                    "allow_real_dispatch"):
                detail = "Pi and Pixhawk connected; physical flight is locked"
                if reason:
                    detail += "; " + reason
                return "completed", detail
            if reason:
                return "completed", "Pi and Pixhawk connected; flight blocked: " + reason
            return "completed", "Pi and Pixhawk connected; basic preflight passed (no command sent)"
        except (HTTPError, URLError, OSError, KeyError, ValueError, TypeError) as exc:
            return "completed", "Pi reached; Pixhawk status unavailable: " + type(exc).__name__
    # A local, explicitly armed bench option lets the authenticated dashboard
    # prove its command path without creating a mission.  It is never used for
    # ESP microphone alerts and calls only the API's normal arm/disarm check.
    if command.get("node_id") == "operator-bench":
        if os.environ.get("VANNI_BENCH_WEB_TEST", "") != "1":
            return "rejected", "props-off bench mode is disabled on the Pi"
        if not pilot_ready:
            return "rejected", "pilot/RC readiness has not been confirmed locally"
        return request_props_off_check(api_url, api_token)
    if not enabled:
        return "rejected", "real flight mode is locked on the Pi"
    if not pilot_ready:
        return "rejected", "pilot/RC readiness has not been confirmed locally"
    if len(api_token) < 32:
        return "rejected", "local flight API token is not configured"
    try:
        with urlopen(api_url + "/telemetry", timeout=3) as response:
            telemetry = json.load(response)
        if allow_missing_battery:
            with urlopen(api_url + "/health", timeout=3) as response:
                limits = json.load(response).get("flight_limits", {})
            if (limits.get("max_mission_duration_s", 9999) > 120 or
                    limits.get("geofence_radius_m", 9999) > 60 or
                    limits.get("allow_real_dispatch") is not True or
                    not 0.5 <= float(limits.get("cruise_altitude_m", 9999)) <= 1.0 or
                    not 0.1 <= float(limits.get("cruise_speed_ms", 9999)) <= 0.5):
                return "rejected", "prototype flight API limits are not configured"
        reason = real_flight_preflight(telemetry, float(command["lat"]),
                                       float(command["lon"]), max_target_m,
                                       allow_missing_battery)
        if reason:
            return "rejected", reason
        payload = json.dumps({"lat": command["lat"], "lon": command["lon"],
                              "incident_type": "operator_real_test",
                              "priority": "high", "deliver_kit": False,
                              **({"hover_s": 0}
                                 if allow_missing_battery else {})}).encode()
        request = Request(api_url + "/trigger", payload,
            headers={"Content-Type": "application/json", "X-API-Key": api_token},
            method="POST")
        with urlopen(request, timeout=5) as response:
            result = json.load(response)
        if result.get("status") != "queued" or not result.get("mission_id"):
            return "rejected", "flight API did not confirm a queued mission"
        return "queued", "mission " + str(result["mission_id"])
    except (HTTPError, URLError, OSError, KeyError, ValueError, TypeError) as exc:
        return "rejected", "local flight API unavailable or refused request: " + type(exc).__name__


def request_props_off_check(api_url: str, api_token: str) -> tuple[str, str]:
    if len(api_token) < 32:
        return "rejected", "local flight API token is not configured"
    try:
        request = Request(api_url + "/bench/props-off-arm-check", b"{}",
            headers={"Content-Type": "application/json", "X-API-Key": api_token},
            method="POST")
        with urlopen(request, timeout=12) as response:
            result = json.load(response)
        if result.get("ok") is not True or result.get("armed_observed") is not True:
            return "rejected", "props-off bench API did not confirm arm/disarm"
        return "completed", "props-off arm/disarm check completed"
    except (HTTPError, URLError, OSError, KeyError, ValueError, TypeError) as exc:
        return "rejected", "props-off bench API unavailable or refused request: " + type(exc).__name__


def real_test_loop(relay_url: str, token: str, stop: threading.Event) -> None:
    """Cloud can request a test; only local hardware and config can permit it."""
    headers = {"Authorization": "Bearer " + token}
    api_url = os.environ.get("VANNI_FLIGHT_API_URL", "http://127.0.0.1:8000").rstrip("/")
    api_token = os.environ.get("VANNI_FLIGHT_API_TOKEN", "")
    enabled = os.environ.get("VANNI_REAL_MODE", "") == "1"
    pilot_ready = os.environ.get("VANNI_PILOT_READY", "") == "1"
    allow_missing_battery = os.environ.get("VANNI_PROTOTYPE_NO_BATTERY", "") == "1"
    try:
        max_target_m = min(5000.0, max(50.0, float(os.environ.get(
            "VANNI_REAL_MAX_TARGET_M", "1000"))))
    except ValueError:
        max_target_m = 1000.0
    while not stop.is_set():
        try:
            claim = Request(relay_url + "/edge/real-test/claim/next", b"{}",
                headers={**headers, "Content-Type": "application/json"}, method="POST")
            with urlopen(claim, timeout=8) as response:
                command = json.load(response).get("command")
            if command:
                status, detail = process_real_test(command, api_url, api_token,
                                                    enabled, pilot_ready, max_target_m,
                                                    allow_missing_battery)
                result = json.dumps({"status": status, "detail": detail}).encode()
                report = Request(relay_url + "/edge/real-test/result/" + command["id"], result,
                    headers={**headers, "Content-Type": "application/json"}, method="POST")
                with urlopen(report, timeout=8):
                    pass
                print(f"Real test {command['id']}: {status}: {detail}", flush=True)
        except (HTTPError, URLError, OSError, ValueError, KeyError) as exc:
            print(f"Real test control unavailable: {type(exc).__name__}", flush=True)
        stop.wait(2)


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
    with AlertServer((args.host, args.port), key, load_nodes(args.registry),
                     args.database, args.relay_url) as server:
        print(f"Listening on {args.host}:{args.port}; dispatch LOCKED_BENCH_ONLY", flush=True)
        relay_stop = threading.Event()
        relay_thread = None
        real_thread = None
        if args.relay_url and args.relay_token:
            relay_thread = threading.Thread(target=cloud_relay_loop,
                args=(server, args.relay_url.rstrip("/"), args.relay_token, relay_stop), daemon=True)
            relay_thread.start()
            print("Cloud relay polling enabled; flight dispatch remains locked", flush=True)
            real_thread = threading.Thread(target=real_test_loop,
                args=(args.relay_url.rstrip("/"), args.relay_token, relay_stop), daemon=True)
            real_thread.start()
        server.serve_forever()
        relay_stop.set()
        if relay_thread:
            relay_thread.join(timeout=3)
        if real_thread:
            real_thread.join(timeout=3)


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
