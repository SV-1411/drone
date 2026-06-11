"""SQLite persistence for mission history.

The in-memory queue remains the source of truth while the process lives;
this store makes the incident log survive restarts. Missions left in
``queued``/``running`` by a crash are marked ``interrupted`` on next boot.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from typing import List, Optional

log = logging.getLogger("trigger_api.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    mission_id    TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    target_lat    REAL NOT NULL,
    target_lon    REAL NOT NULL,
    altitude_m    REAL NOT NULL,
    hover_s       INTEGER NOT NULL,
    priority      TEXT NOT NULL,
    incident_type TEXT NOT NULL,
    queued_at     REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL,
    final_state   TEXT
);
CREATE INDEX IF NOT EXISTS idx_missions_queued_at ON missions (queued_at DESC);
"""


class MissionStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._mark_interrupted()

    def _mark_interrupted(self) -> None:
        """Anything still queued/running belongs to a previous process."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE missions SET status='interrupted', finished_at=? "
                "WHERE status IN ('queued','running')",
                (time.time(),),
            )
            self._conn.commit()
        if cur.rowcount:
            log.warning("marked %d mission(s) from a previous run as interrupted", cur.rowcount)

    def upsert(self, qm) -> None:
        """Persist a QueuedMission's current state (insert or update)."""
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO missions (mission_id, status, target_lat, target_lon, altitude_m,"
                    " hover_s, priority, incident_type, queued_at, started_at, finished_at, final_state)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(mission_id) DO UPDATE SET"
                    " status=excluded.status, started_at=excluded.started_at,"
                    " finished_at=excluded.finished_at, final_state=excluded.final_state",
                    (
                        qm.spec.mission_id, qm.status, qm.spec.target_lat, qm.spec.target_lon,
                        qm.spec.altitude_m, qm.spec.hover_s, qm.spec.priority,
                        qm.spec.incident_type, qm.queued_at, qm.started_at,
                        qm.finished_at, qm.final_state,
                    ),
                )
                self._conn.commit()
        except Exception:
            # Persistence must never take down the dispatch path.
            log.exception("failed to persist mission %s", qm.spec.mission_id)

    def load_recent(self, limit: int = 200) -> List[dict]:
        """Rows for missions from previous runs, newest first."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT mission_id, status, target_lat, target_lon, altitude_m, hover_s,"
                " priority, incident_type, queued_at, started_at, finished_at, final_state"
                " FROM missions ORDER BY queued_at DESC LIMIT ?",
                (limit,),
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def prune(self, keep: int) -> None:
        try:
            with self._lock:
                self._conn.execute(
                    "DELETE FROM missions WHERE mission_id NOT IN"
                    " (SELECT mission_id FROM missions ORDER BY queued_at DESC LIMIT ?)",
                    (keep,),
                )
                self._conn.commit()
        except Exception:
            log.exception("failed to prune mission store")

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass


def open_store(db_path: str) -> Optional[MissionStore]:
    """Open the store; on any failure return None and run memory-only."""
    try:
        return MissionStore(db_path)
    except Exception:
        log.exception("could not open mission store at %s — running memory-only", db_path)
        return None
