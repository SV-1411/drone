"""Thread-safe live telemetry store for an external ArduPilot/Gazebo SITL vehicle.

The Render service remains usable without SITL. When a local/remote SITL bridge
posts telemetry, /drone_state prefers this source while it is fresh.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

_lock = threading.RLock()
_state: Dict[str, Any] = {}
_last_update = 0.0


def update(**values: Any) -> Dict[str, Any]:
    global _last_update
    with _lock:
        _state.update(values)
        _state["source"] = "ARDUPILOT_SITL_GAZEBO"
        _state["updated_at"] = time.time()
        _last_update = _state["updated_at"]
        return dict(_state)


def snapshot(max_age_s: float = 5.0) -> Optional[Dict[str, Any]]:
    with _lock:
        if not _state or time.time() - _last_update > max_age_s:
            return None
        return dict(_state)


def clear() -> None:
    global _state, _last_update
    with _lock:
        _state = {}
        _last_update = 0.0
