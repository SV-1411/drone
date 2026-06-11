"""Fast unit tests for the safety-critical logic — no SITL required.

Run from project root:

    python -m pytest tests/test_units.py -v

Covers the failsafe monitor (thresholds, GPS debounce, escalation, no-spam),
the mission queue (priority order, depth cap, history pruning, cancel),
the SQLite mission store, request validation, and env-driven config.
"""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flight_core.config import Config
from flight_core.failsafe_handler import FailsafeHandler
from flight_core.mission_executor import MissionSpec, MissionState
from trigger_api.mission_queue import MissionQueue, QueueFull, new_mission_id
from trigger_api.models import TriggerRequest, WaypointRequest
from trigger_api.store import MissionStore


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _Battery:
    def __init__(self, level=100, voltage=12.6):
        self.level = level
        self.voltage = voltage


class _Gps:
    def __init__(self, fix_type=3, satellites_visible=10):
        self.fix_type = fix_type
        self.satellites_visible = satellites_visible


class _Loc:
    def __init__(self, lat, lon, alt=15.0):
        self.lat, self.lon, self.alt = lat, lon, alt


class _Location:
    def __init__(self, lat, lon, alt=15.0):
        self.global_relative_frame = _Loc(lat, lon, alt)


class FakeVehicle:
    """Just enough of the dronekit Vehicle surface for the failsafe monitor."""

    def __init__(self, lat=28.6139, lon=77.2090):
        self.battery = _Battery()
        self.gps_0 = _Gps()
        self.location = _Location(lat, lon)
        self.armed = False


class FakeExecutor:
    """Stub executor for queue tests: records mission order, optionally blocks."""

    def __init__(self, result=MissionState.COMPLETED, block: bool = False):
        self.result = result
        self.ran = []
        self.abort_requests = []
        self.release = threading.Event()
        self.started = threading.Event()
        self.block = block

    def run_mission(self, spec):
        self.ran.append(spec.mission_id)
        self.started.set()
        if self.block:
            self.release.wait(timeout=10)
        return self.result

    def request_abort(self, reason=""):
        self.abort_requests.append(reason)
        self.release.set()


CFG = Config()  # all defaults: low_battery 20, critical 10, geofence 5000 m, gps debounce 3


def make_failsafe(vehicle, **cfg_overrides):
    cfg = Config(**cfg_overrides) if cfg_overrides else CFG
    return FailsafeHandler(vehicle, cfg, mission_started_at=time.time())


# ---------------------------------------------------------------------------
# Failsafe monitor
# ---------------------------------------------------------------------------

class TestFailsafes:
    def test_no_failsafe_when_healthy(self):
        fs = make_failsafe(FakeVehicle())
        fs._check_battery(); fs._check_gps(); fs._check_geofence(); fs._check_timeout()
        assert not fs.triggered
        assert fs.required_action == "NONE"

    def test_low_battery_triggers_rtl(self):
        v = FakeVehicle(); v.battery.level = 15
        fs = make_failsafe(v)
        fs._check_battery()
        assert fs.triggered and fs.required_action == "RTL"
        assert [e.name for e in fs.events()] == ["low_battery"]

    def test_critical_battery_triggers_land(self):
        v = FakeVehicle(); v.battery.level = 8
        fs = make_failsafe(v)
        fs._check_battery()
        assert fs.triggered and fs.required_action == "LAND"

    def test_low_battery_escalates_to_critical_land(self):
        v = FakeVehicle(); v.battery.level = 15
        fs = make_failsafe(v)
        fs._check_battery()
        assert fs.required_action == "RTL"
        v.battery.level = 8
        fs._check_battery()
        assert fs.required_action == "LAND"

    def test_land_never_downgrades_to_rtl(self):
        v = FakeVehicle()
        v.gps_0.fix_type = 0
        fs = make_failsafe(v)
        for _ in range(3):
            fs._check_gps()
        assert fs.required_action == "LAND"
        # later RTL-severity events must not weaken the demanded action
        fs.mission_started_at = time.time() - 99999
        fs._check_timeout()
        assert fs.required_action == "LAND"

    def test_battery_event_fires_only_once(self):
        v = FakeVehicle(); v.battery.level = 5
        fs = make_failsafe(v)
        for _ in range(10):
            fs._check_battery()
        assert len([e for e in fs.events() if e.name == "critical_battery"]) == 1

    def test_gps_glitch_is_debounced(self):
        v = FakeVehicle()
        fs = make_failsafe(v)
        v.gps_0.fix_type = 0          # two bad samples — below threshold of 3
        fs._check_gps(); fs._check_gps()
        assert not fs.triggered
        v.gps_0.fix_type = 3          # recovery resets the streak
        fs._check_gps()
        v.gps_0.fix_type = 0
        fs._check_gps(); fs._check_gps()
        assert not fs.triggered

    def test_sustained_gps_loss_triggers_land(self):
        v = FakeVehicle(); v.gps_0.fix_type = 0
        fs = make_failsafe(v)
        for _ in range(3):
            fs._check_gps()
        assert fs.triggered and fs.required_action == "LAND"

    def test_geofence_breach_triggers_rtl(self):
        # ~0.1 deg latitude ≈ 11 km from home — well past the 5 km fence
        v = FakeVehicle(lat=28.7139, lon=77.2090)
        fs = make_failsafe(v)
        fs._check_geofence()
        assert fs.triggered and fs.required_action == "RTL"

    def test_mission_timeout_triggers_rtl(self):
        fs = make_failsafe(FakeVehicle())
        fs.mission_started_at = time.time() - (CFG.max_mission_duration_s + 5)
        fs._check_timeout()
        assert fs.triggered and fs.required_action == "RTL"


# ---------------------------------------------------------------------------
# Mission queue
# ---------------------------------------------------------------------------

def _spec(priority="normal", mission_id=None):
    return MissionSpec(
        mission_id=mission_id or new_mission_id(),
        target_lat=28.62, target_lon=77.215,
        altitude_m=15.0, hover_s=5, priority=priority,
    )


class TestMissionQueue:
    def test_priority_ordering(self):
        q = MissionQueue(FakeExecutor())
        low = q.enqueue(_spec("low"))
        crit = q.enqueue(_spec("critical"))
        norm = q.enqueue(_spec("normal"))
        order = [m.spec.mission_id for m in q._pending]
        assert order == [crit.spec.mission_id, norm.spec.mission_id, low.spec.mission_id]

    def test_depth_cap_raises_queue_full(self):
        q = MissionQueue(FakeExecutor(), max_depth=2)
        q.enqueue(_spec()); q.enqueue(_spec())
        with pytest.raises(QueueFull):
            q.enqueue(_spec())

    def test_history_pruned_but_active_kept(self):
        q = MissionQueue(FakeExecutor(), max_depth=100, history_limit=3)
        finished = [q.enqueue(_spec()) for _ in range(4)]
        for qm in finished:
            qm.status = "done"
            q._pending.clear()
        q.enqueue(_spec())  # 5th entry triggers prune of oldest finished
        assert len(q._history) <= 4

    def test_cancel_queued_mission(self):
        q = MissionQueue(FakeExecutor())
        qm = q.enqueue(_spec())
        assert q.cancel(qm.spec.mission_id) == "cancelled"
        assert qm.status == "cancelled"
        assert q.depth() == 0

    def test_cancel_running_mission_requests_abort(self):
        ex = FakeExecutor(result=MissionState.ABORTED, block=True)
        q = MissionQueue(ex)
        q.start()
        try:
            qm = q.enqueue(_spec())
            assert ex.started.wait(timeout=5), "worker never started the mission"
            assert q.cancel(qm.spec.mission_id) == "aborting"
            assert ex.abort_requests, "executor.request_abort was not called"
            deadline = time.time() + 5
            while qm.status == "running" and time.time() < deadline:
                time.sleep(0.05)
            assert qm.status == "aborted"
        finally:
            ex.release.set()
            q.stop()

    def test_cancel_finished_mission_returns_none(self):
        q = MissionQueue(FakeExecutor())
        qm = q.enqueue(_spec())
        qm.status = "done"
        q._pending.clear()
        assert q.cancel(qm.spec.mission_id) is None

    def test_worker_executes_and_records_result(self):
        ex = FakeExecutor()
        q = MissionQueue(ex)
        q.start()
        try:
            qm = q.enqueue(_spec())
            deadline = time.time() + 5
            while qm.status != "done" and time.time() < deadline:
                time.sleep(0.05)
            assert qm.status == "done"
            assert qm.final_state == "COMPLETED"
            assert ex.ran == [qm.spec.mission_id]
        finally:
            q.stop()


# ---------------------------------------------------------------------------
# Mission store (SQLite persistence)
# ---------------------------------------------------------------------------

class TestMissionStore:
    def test_roundtrip_and_interrupted_marking(self, tmp_path):
        db = str(tmp_path / "missions.db")
        store = MissionStore(db)
        q = MissionQueue(FakeExecutor(), store=store)
        qm = q.enqueue(_spec(mission_id="abc123def456"))
        rows = store.load_recent()
        assert rows[0]["mission_id"] == "abc123def456"
        assert rows[0]["status"] == "queued"
        store.close()

        # a new process marks the leftover 'queued' row as interrupted
        store2 = MissionStore(db)
        rows = store2.load_recent()
        assert rows[0]["status"] == "interrupted"
        store2.close()

    def test_prune_keeps_newest(self, tmp_path):
        db = str(tmp_path / "missions.db")
        store = MissionStore(db)
        q = MissionQueue(FakeExecutor(), max_depth=100, store=store)
        for i in range(5):
            qm = q.enqueue(_spec())
            qm.queued_at = time.time() + i  # strictly increasing
            store.upsert(qm)
        store.prune(keep=2)
        assert len(store.load_recent()) == 2
        store.close()


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

class TestModels:
    def test_valid_trigger(self):
        r = TriggerRequest(lat=28.62, lon=77.215, priority="high")
        assert r.lat == 28.62

    @pytest.mark.parametrize("bad", [{"lat": 91}, {"lat": -91}, {"lon": 181}, {"lon": -181}])
    def test_trigger_rejects_out_of_range_coords(self, bad):
        kwargs = {"lat": 28.62, "lon": 77.215, **bad}
        with pytest.raises(Exception):
            TriggerRequest(**kwargs)

    def test_trigger_rejects_bad_priority(self):
        with pytest.raises(Exception):
            TriggerRequest(lat=28.62, lon=77.215, priority="urgent")

    @pytest.mark.parametrize("alt", [-5, 0, 1.9, 121, 10000])
    def test_trigger_rejects_unsafe_altitude(self, alt):
        with pytest.raises(Exception):
            TriggerRequest(lat=28.62, lon=77.215, altitude_m=alt)

    @pytest.mark.parametrize("hover", [-1, 3601])
    def test_trigger_rejects_bad_hover(self, hover):
        with pytest.raises(Exception):
            TriggerRequest(lat=28.62, lon=77.215, hover_s=hover)

    def test_waypoint_rejects_out_of_range(self):
        with pytest.raises(Exception):
            WaypointRequest(lat=999, lon=77.215)
        with pytest.raises(Exception):
            WaypointRequest(lat=28.62, lon=77.215, alt=500)

    def test_waypoint_valid(self):
        w = WaypointRequest(lat=28.62, lon=77.215, alt=20)
        assert w.alt == 20


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_from_env_reads_at_construction(self, monkeypatch):
        monkeypatch.setenv("GEOFENCE_RADIUS", "1234.5")
        monkeypatch.setenv("API_TOKEN", "secret")
        cfg = Config.from_env()
        assert cfg.geofence_radius_m == 1234.5
        assert cfg.api_token == "secret"

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("GEOFENCE_RADIUS", "not-a-number")
        cfg = Config.from_env()
        assert cfg.geofence_radius_m == 5000.0

    def test_resolved_db_path_default(self):
        cfg = Config(log_dir="logs")
        assert cfg.resolved_db_path == os.path.join("logs", "missions.db")
