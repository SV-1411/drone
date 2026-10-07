"""Best-effort cloud relay for signed ESP sensing-node alerts.

This queue uses a local SQLite file and is suitable for prototype testing only.
Render's free filesystem is ephemeral, so production use requires durable storage.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import secrets
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
        self.operator_key = os.environ.get("VANNI_OPERATOR_KEY", "")
        self.db_path = Path(os.environ.get("VANNI_RELAY_DB", "/tmp/vannikawachh-edge-relay.sqlite3"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.db_conn() as db:
            db.execute("CREATE TABLE IF NOT EXISTS edge_alerts (node_id TEXT NOT NULL, seq INTEGER NOT NULL, body BLOB NOT NULL, signature TEXT NOT NULL, created REAL NOT NULL, acked REAL, PRIMARY KEY(node_id, seq))")
            db.execute("CREATE TABLE IF NOT EXISTS real_commands (id TEXT PRIMARY KEY, node_id TEXT NOT NULL, seq INTEGER NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, created REAL NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE IF NOT EXISTS edge_verifications (node_id TEXT NOT NULL, seq INTEGER NOT NULL, confirmed INTEGER NOT NULL, backend TEXT NOT NULL, score REAL NOT NULL, received REAL NOT NULL, PRIMARY KEY(node_id, seq))")
            db.execute("CREATE TABLE IF NOT EXISTS mobile_incidents (id TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, accuracy_m REAL NOT NULL, source TEXT NOT NULL, verified INTEGER NOT NULL, audio_score REAL NOT NULL, created REAL NOT NULL, status TEXT NOT NULL)")

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

    def authenticate_operator(self, supplied: str) -> bool:
        return len(self.operator_key) >= 32 and hmac.compare_digest(
            supplied, self.operator_key)

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

    def recent(self, limit: int = 20) -> list[dict]:
        """Public, redacted event history for the dashboard (never raw packets/keys)."""
        import json
        limit = max(1, min(int(limit), 50))
        with self.db_conn() as db:
            rows = db.execute(
                "SELECT a.node_id, a.seq, a.body, a.created, a.acked, "
                "v.confirmed, v.backend, v.score FROM edge_alerts a "
                "LEFT JOIN edge_verifications v ON v.node_id=a.node_id AND v.seq=a.seq "
                "ORDER BY a.created DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {"node_id": node_id, "seq": seq,
             "lat": json.loads(body)["lat"], "lon": json.loads(body)["lon"],
             "sound_score": json.loads(body)["sound_score"],
             "received_at": created, "pi_received": acked is not None,
             "audio_received": confirmed is not None,
             "audio_confirmed": bool(confirmed) if confirmed is not None else None,
             "audio_backend": backend, "audio_score": score}
            for node_id, seq, body, created, acked, confirmed, backend, score in rows
        ]

    def record_verification(self, node_id: str, seq: int, confirmed: bool,
                            backend: str, score: float) -> bool:
        if not node_id or type(seq) is not int or seq < 1 or not 0 <= score <= 1:
            raise ValueError("invalid verification values")
        with self.db_conn() as db:
            known = db.execute("SELECT 1 FROM edge_alerts WHERE node_id=? AND seq=?",
                               (node_id, seq)).fetchone()
            if not known:
                return False
            db.execute("INSERT OR REPLACE INTO edge_verifications VALUES (?,?,?,?,?,?)",
                       (node_id, seq, int(confirmed), backend[:80], score, time.time()))
        return True

    def ack(self, node_id: str, seq: int) -> bool:
        with self.db_conn() as db:
            cur = db.execute("UPDATE edge_alerts SET acked=? WHERE node_id=? AND seq=? AND acked IS NULL", (time.time(), node_id, seq))
            return cur.rowcount == 1

    def queue_real_test(self) -> dict:
        """Create a short-lived operator test at the latest signed node position."""
        recent = self.recent(1)
        if not recent or time.time() - recent[0]["received_at"] > 600:
            raise ValueError("no recent signed sensing-node alert")
        event = recent[0]
        command_id = secrets.token_urlsafe(18)
        with self.db_conn() as db:
            active = db.execute("SELECT 1 FROM real_commands WHERE status IN "
                                "('pending','claimed') AND created > ? LIMIT 1",
                                (time.time() - 60,)).fetchone()
            if active:
                raise ValueError("a real test request is already in progress")
            db.execute("INSERT INTO real_commands "
                       "(id,node_id,seq,lat,lon,created,status) "
                       "VALUES (?,?,?,?,?,?,'pending')",
                       (command_id, event["node_id"], event["seq"],
                        event["lat"], event["lon"], time.time()))
        return {"id": command_id, "status": "pending", "node_id": event["node_id"],
                "target": [event["lat"], event["lon"]]}

    def queue_props_off_bench_test(self) -> dict:
        """Queue a one-time operator bench request without a node alert.

        The Pi recognises the reserved identity and requires its separate
        local props-off gate before it can send a normal arm request.
        """
        command_id = secrets.token_urlsafe(18)
        with self.db_conn() as db:
            active = db.execute("SELECT 1 FROM real_commands WHERE status IN "
                                "('pending','claimed') AND created > ? LIMIT 1",
                                (time.time() - 60,)).fetchone()
            if active:
                raise ValueError("a real test request is already in progress")
            db.execute("INSERT INTO real_commands "
                       "(id,node_id,seq,lat,lon,created,status) "
                       "VALUES (?,'operator-bench',0,0,0,?,'pending')",
                       (command_id, time.time()))
        return {"id": command_id, "status": "pending", "kind": "props_off_bench"}

    def record_mobile_incident(self, lat: float, lon: float, accuracy_m: float,
                               source: str, verified: bool, audio_score: float = 0.0) -> dict:
        """Accept a public phone report; this does not create a flight command."""
        values = (lat, lon, accuracy_m, audio_score)
        if (not all(math.isfinite(float(value)) for value in values)
                or not -90 <= lat <= 90 or not -180 <= lon <= 180
                or (lat == 0 and lon == 0) or not 0 < accuracy_m <= 10_000
                or not 0 <= audio_score <= 1 or source not in ("button", "voice")):
            raise ValueError("invalid mobile report")
        now = time.time()
        incident_id = secrets.token_urlsafe(18)
        with self.db_conn() as db:
            recent = db.execute("SELECT count(*) FROM mobile_incidents WHERE created > ?",
                                (now - 60,)).fetchone()[0]
            if recent >= 30:
                raise ValueError("mobile reporting is temporarily busy")
            db.execute("INSERT INTO mobile_incidents VALUES (?,?,?,?,?,?,?,?,?)",
                       (incident_id, lat, lon, accuracy_m, source, int(verified),
                        audio_score, now, "reported"))
        return {"id": incident_id, "status": "reported", "verified": bool(verified)}

    def recent_mobile(self, limit: int = 10) -> list[dict]:
        with self.db_conn() as db:
            rows = db.execute("SELECT id,lat,lon,accuracy_m,source,verified,audio_score,created,status "
                              "FROM mobile_incidents ORDER BY created DESC LIMIT ?",
                              (max(1, min(limit, 50)),)).fetchall()
        return [dict(zip(("id", "lat", "lon", "accuracy_m", "source", "verified",
                          "audio_score", "created", "status"), row)) for row in rows]

    def queue_mobile_real_test(self, incident_id: str) -> dict:
        """Queue only a fresh server-verified phone report after operator approval."""
        now = time.time()
        command_id = secrets.token_urlsafe(18)
        with self.db_conn() as db:
            row = db.execute("SELECT lat,lon,accuracy_m,source,verified,created,status "
                             "FROM mobile_incidents WHERE id=?", (incident_id,)).fetchone()
            if row is None or row[6] != "reported":
                raise ValueError("mobile incident is unavailable")
            lat, lon, accuracy, source, verified, created, _ = row
            if source != "voice" or not verified:
                raise ValueError("button reports cannot request physical flight")
            if now - created > 120 or accuracy > 50:
                raise ValueError("fresh phone GPS within 50 m accuracy is required")
            active = db.execute("SELECT 1 FROM real_commands WHERE status IN "
                                "('pending','claimed') AND created > ? LIMIT 1",
                                (now - 60,)).fetchone()
            if active:
                raise ValueError("a real test request is already in progress")
            db.execute("INSERT INTO real_commands (id,node_id,seq,lat,lon,created,status) "
                       "VALUES (?,?,?,?,?,?,'pending')",
                       (command_id, "phone-" + incident_id, 0, lat, lon, now))
            db.execute("UPDATE mobile_incidents SET status='approved' WHERE id=?", (incident_id,))
        return {"id": command_id, "status": "pending", "target": [lat, lon],
                "mobile_incident_id": incident_id}

    def claim_real_test(self) -> dict | None:
        """At-most-once claim: a stale/offline command never launches later."""
        now = time.time()
        with self.db_conn() as db:
            db.execute("UPDATE real_commands SET status='expired' "
                       "WHERE status='pending' AND created < ?", (now - 60,))
            row = db.execute("SELECT id,node_id,seq,lat,lon FROM real_commands "
                             "WHERE status='pending' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            updated = db.execute("UPDATE real_commands SET status='claimed' "
                                 "WHERE id=? AND status='pending'", (row[0],))
            if updated.rowcount != 1:
                return None
        return {"id": row[0], "node_id": row[1], "seq": row[2],
                "lat": row[3], "lon": row[4]}

    def finish_real_test(self, command_id: str, status: str, detail: str) -> bool:
        if status not in ("rejected", "queued", "completed"):
            raise ValueError("invalid command status")
        with self.db_conn() as db:
            updated = db.execute("UPDATE real_commands SET status=?, detail=? "
                                 "WHERE id=? AND status='claimed'",
                                 (status, detail[:240], command_id))
            return updated.rowcount == 1

    def real_test_status(self, command_id: str) -> dict | None:
        with self.db_conn() as db:
            row = db.execute("SELECT id,status,detail,created FROM real_commands "
                             "WHERE id=?", (command_id,)).fetchone()
        return ({"id": row[0], "status": row[1], "detail": row[2],
                 "created": row[3]} if row else None)


relay = EdgeRelay()
