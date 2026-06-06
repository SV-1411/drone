"""Single-drone mission queue.

We have one physical drone, so missions execute serially. Higher-priority
missions go to the head of the queue. A worker thread pulls one mission at a
time and hands it to the MissionExecutor.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from flight_core.mission_executor import MissionExecutor, MissionSpec, MissionState

log = logging.getLogger("trigger_api.queue")

_PRIORITY = {"critical": 0, "high": 1, "normal": 2, "low": 3}


@dataclass
class QueuedMission:
    spec: MissionSpec
    queued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    final_state: Optional[str] = None
    status: str = "queued"  # queued | running | done | failed | aborted

    def priority_key(self) -> int:
        return _PRIORITY.get(self.spec.priority, 2)


class MissionQueue:
    def __init__(self, executor: MissionExecutor):
        self.executor = executor
        self._pending: Deque[QueuedMission] = deque()
        self._history: Dict[str, QueuedMission] = {}
        self._current: Optional[QueuedMission] = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run, name="mission-queue", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout=2.0)

    def enqueue(self, spec: MissionSpec) -> QueuedMission:
        qm = QueuedMission(spec=spec)
        with self._lock:
            self._pending.append(qm)
            self._sort_pending_locked()
            self._history[spec.mission_id] = qm
        log.info("queued mission %s (priority=%s) — depth=%d", spec.mission_id, spec.priority, len(self._pending))
        self._wake.set()
        return qm

    def get(self, mission_id: str) -> Optional[QueuedMission]:
        with self._lock:
            return self._history.get(mission_id)

    def list_recent(self, limit: int = 50) -> List[QueuedMission]:
        with self._lock:
            items = list(self._history.values())
        items.sort(key=lambda m: m.queued_at, reverse=True)
        return items[:limit]

    def current(self) -> Optional[QueuedMission]:
        with self._lock:
            return self._current

    def _sort_pending_locked(self) -> None:
        items = list(self._pending)
        items.sort(key=lambda m: (m.priority_key(), m.queued_at))
        self._pending = deque(items)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=1.0)
            self._wake.clear()
            while True:
                with self._lock:
                    if not self._pending:
                        break
                    qm = self._pending.popleft()
                    self._current = qm
                self._execute(qm)
                with self._lock:
                    self._current = None

    def _execute(self, qm: QueuedMission) -> None:
        qm.status = "running"
        qm.started_at = time.time()
        try:
            state = self.executor.run_mission(qm.spec)
            qm.final_state = state.value
            if state == MissionState.COMPLETED:
                qm.status = "done"
            elif state == MissionState.ABORTED:
                qm.status = "aborted"
            else:
                qm.status = "failed"
        except Exception as exc:
            log.exception("mission %s crashed: %s", qm.spec.mission_id, exc)
            qm.status = "failed"
            qm.final_state = "FAILED"
        finally:
            qm.finished_at = time.time()


def new_mission_id() -> str:
    return uuid.uuid4().hex[:12]
