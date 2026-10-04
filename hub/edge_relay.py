"""Best-effort cloud relay for signed ESP sensing-node alerts.

This queue uses a local SQLite file and is suitable for prototype testing only.
Render's free filesystem is ephemeral, so production use requires durable storage.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

MAX_BODY = 2048


class EdgeRelay:
    def __init__(self) -> None:
        raw_key = os.environ.get("VANNI_ALERT_KEY", "")
        try:
            self.alert_key = bytes.fromhex(raw_key)
        except ValueError:
            self.alert_key = b""
        self.pi_token = os.environ.get("VANNI_RELAY_PI_TOKEN", "")
        self.db_path = Path(os.environ.get("VANNI_RELAY_DB", "/tmp/vannikawachh-edge-relay.sqlite3"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.db_conn() as db:
            db.execute("CREATE TABLE IF NOT EXISTS edge_alerts (node_id TEXT NOT NULL, seq INTEGER NOT NULL, body BLOB NOT NULL, signature TEXT NOT NULL, created REAL NOT NULL, acked REAL, PRIMARY KEY(node_id, seq))")

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=5)

    @contextmanager
    def db_conn(self):
        db = self.connect()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def ready(self) -> bool:
        return len(self.alert_key) == 32 and len(self.pi_token) >= 32

    def authenticate_pi(self, authorization: str) -> bool:
        supplied = authorization.removeprefix("Bearer ")
        return bool(self.pi_token) and hmac.compare_digest(supplied, self.pi_token)

    def enqueue(self, body: bytes, signature: str) -> tuple[str, dict | None]:
        if len(body) > MAX_BODY or not body:
            raise ValueError("invalid body size")
        expected = hmac.new(self.alert_key, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            raise PermissionError("invalid signature")
        import json
        event = json.loads(body)
        if not isinstance(event, dict) or event.get("kind") != "sound_level_candidate":
            raise ValueError("unsupported alert")
        node_id, seq = event.get("node_id"), event.get("seq")
        if not isinstance(node_id, str) or type(seq) is not int or seq < 1:
            raise ValueError("invalid event identity")
        lat, lon, score = float(event["lat"]), float(event["lon"]), float(event["sound_score"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= score <= 1):
            raise ValueError("invalid event values")
        with self.db_conn() as db:
            cur = db.execute("INSERT OR IGNORE INTO edge_alerts VALUES (?, ?, ?, ?, ?, NULL)",
                             (node_id, seq, body, signature.lower(), time.time()))
            status = "queued" if cur.rowcount else "duplicate"
        return status, event

    def pending(self, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 100))
        import base64
        with self.db_conn() as db:
            rows = db.execute("SELECT node_id, seq, body, signature FROM edge_alerts WHERE acked IS NULL ORDER BY created LIMIT ?", (limit,)).fetchall()
        return [{"node_id": n, "seq": s, "body_b64": base64.b64encode(b).decode("ascii"), "signature": sig} for n, s, b, sig in rows]

    def ack(self, node_id: str, seq: int) -> bool:
        with self.db_conn() as db:
            cur = db.execute("UPDATE edge_alerts SET acked=? WHERE node_id=? AND seq=? AND acked IS NULL", (time.time(), node_id, seq))
            return cur.rowcount == 1


relay = EdgeRelay()
