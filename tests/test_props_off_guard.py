"""Safety guard tests for the dashboard props-off bench endpoint."""

import importlib

import pytest
from fastapi import HTTPException

from flight_core.config import Config
from flight_core.mission_executor import MissionExecutor


def test_props_off_check_requires_local_physical_confirmation(monkeypatch):
    api_main = importlib.import_module("trigger_api.main")
    monkeypatch.setattr(
        api_main,
        "CONFIG",
        Config(mavlink_connection="/dev/serial0,57600", api_token="bench-secret"),
    )
    monkeypatch.delenv("BENCH_PROPS_REMOVED", raising=False)
    with pytest.raises(HTTPException) as exc:
        api_main.props_off_arm_check()
    assert exc.value.status_code == 503


def test_bench_check_uses_normal_arm_then_confirms_disarm(tmp_path, monkeypatch):
    class Vehicle:
        is_armable = False  # DroneKit can be stale even when Pixhawk accepts arm.

        def __init__(self):
            self._armed = False
            self.writes = []

        @property
        def armed(self):
            return self._armed

        @armed.setter
        def armed(self, value):
            self.writes.append(value)
            self._armed = value

    executor = MissionExecutor(Config(log_dir=str(tmp_path)))
    vehicle = Vehicle()
    executor.vehicle = vehicle
    monkeypatch.setattr(executor, "ensure_connected", lambda: None)
    monkeypatch.setattr("flight_core.mission_executor.time.sleep", lambda _: None)
    result = executor.props_off_arm_check(spin_seconds=0.5)
    assert result["armed_observed"] is True
    assert vehicle.writes == [True, False]
    assert vehicle.armed is False
