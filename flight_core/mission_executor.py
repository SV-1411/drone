"""Mission executor — the autonomous flight state machine.

A mission is a single end-to-end run: connect → GPS lock → arm → takeoff →
goto waypoint(s) → hover → RTL → land → done. Every transition is logged with
a timestamp; no phase ever waits for human input.

Safety invariants enforced here:
- Abort paths (failsafe or operator cancel) use the confirmed mode setter
  with the raw-MAVLink fallback — never the bare dronekit setter, which
  ArduCopter 3.3 SITL is known to silently ignore.
- An aborted or failed mission blocks until the vehicle has landed and
  disarmed (or a hard timeout passes) before the executor returns, so the
  queue can never start a new mission against an airborne vehicle.
- A new mission additionally refuses to start while the vehicle is armed.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, List, Optional, Dict, Any

from .camera_recorder import CameraRecorder
from .config import CONFIG, Config
from .failsafe_handler import FailsafeHandler
from .obstacle_avoidance import plan_route, load_obstacles_from_env
from .payload_release import release_kit
from .mavlink_interface import (
    LocationGlobalRelative,
    connect_vehicle,
    haversine_distance_m,
    relative_location,
    wait_for_gps_lock,
)

log = logging.getLogger("flight_core.mission")


class MissionState(str, Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    WAITING_GPS = "WAITING_GPS"
    ARMING = "ARMING"
    TAKEOFF = "TAKEOFF"
    ENROUTE = "ENROUTE"
    HOVERING = "HOVERING"
    DELIVERING = "DELIVERING"
    RTL = "RTL"
    LANDED = "LANDED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"


@dataclass
class Waypoint:
    lat: float
    lon: float
    alt: float


@dataclass
class MissionSpec:
    mission_id: str
    target_lat: float
    target_lon: float
    altitude_m: float
    hover_s: int
    priority: str = "normal"
    incident_type: str = "generic"
    deliver_kit: bool = False           # VanniKawachh: drop the first-aid kit
    extra_waypoints: List[Waypoint] = field(default_factory=list)


@dataclass
class TelemetrySnapshot:
    state: str
    mission_id: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    alt_m: Optional[float]
    heading_deg: Optional[float]
    ground_speed_ms: Optional[float]
    battery_pct: Optional[float]
    battery_voltage: Optional[float]
    gps_fix: Optional[int]
    gps_sats: Optional[int]
    armed: bool
    mode: Optional[str]
    home_lat: float
    home_lon: float
    target_lat: Optional[float]
    target_lon: Optional[float]
    path: List[Dict[str, float]] = field(default_factory=list)
    log_tail: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _setup_logging(log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    root = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        file_handler = logging.FileHandler(os.path.join(log_dir, "mission.log"), encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(fmt))
        root.addHandler(file_handler)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(fmt))
        root.addHandler(stream)
    root.setLevel(logging.INFO)
    return root


class MissionExecutor:
    """Holds the vehicle handle and runs missions one at a time.

    Telemetry is captured into a thread-safe snapshot the API reads on demand.
    Only one mission runs at a time; new triggers enqueue via the API layer.
    """

    # How long the abort path waits for the vehicle to land+disarm before
    # giving up (the vehicle keeps descending either way; we just stop blocking).
    ABORT_LAND_WAIT_S = 240
    # How long run_mission waits for a previous flight to disarm before refusing.
    PREFLIGHT_DISARM_WAIT_S = 120
    # Per-attempt confirmation window for abort-path mode changes.
    ABORT_MODE_TIMEOUT_S = 15

    def __init__(self, config: Config = CONFIG, log_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.vehicle = None
        self._lock = threading.RLock()
        self._connect_lock = threading.Lock()
        self._state: MissionState = MissionState.IDLE
        self._current: Optional[MissionSpec] = None
        self._path: List[Dict[str, float]] = []
        self._log_tail: List[str] = []
        self._extra_waypoints_pending: List[Waypoint] = []
        self._abort_requested = threading.Event()
        self._abort_reason: str = ""
        self._log_cb = log_callback
        self._stop_telemetry = threading.Event()
        self._telemetry_thread: Optional[threading.Thread] = None
        # Known keep-out zones for map-based avoidance (empty -> direct flight).
        self.obstacles = load_obstacles_from_env()
        self.recorder = CameraRecorder(out_dir=os.path.join(config.log_dir, "recordings"))
        _setup_logging(config.log_dir)
        if self.obstacles:
            log.info("loaded %d obstacle keep-out zone(s)", len(self.obstacles))

    # ---------- state plumbing ----------
    def _set_state(self, state: MissionState) -> None:
        with self._lock:
            self._state = state
        self._log(f"state -> {state.value}")

    def _log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"{ts} {msg}"
        log.info(msg)
        with self._lock:
            self._log_tail.append(line)
            if len(self._log_tail) > 200:
                self._log_tail = self._log_tail[-200:]
        if self._log_cb:
            try:
                self._log_cb(line)
            except Exception:
                pass

    @property
    def state(self) -> MissionState:
        with self._lock:
            return self._state

    @property
    def current_mission(self) -> Optional[MissionSpec]:
        with self._lock:
            return self._current

    def add_waypoint(self, wp: Waypoint) -> None:
        """Operator may inject an extra waypoint mid-mission (optional input)."""
        with self._lock:
            self._extra_waypoints_pending.append(wp)
        self._log(f"extra waypoint added: ({wp.lat:.6f},{wp.lon:.6f},{wp.alt:.1f})")

    def request_abort(self, reason: str = "operator cancel") -> None:
        """Ask the running mission to abort (RTL home). Thread-safe; no-op if idle."""
        self._abort_reason = reason
        self._abort_requested.set()
        self._log(f"abort requested: {reason}")

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            v = self.vehicle
            current = self._current
            state = self._state
            path = list(self._path[-500:])  # cap memory
            log_tail = list(self._log_tail[-20:])

        lat = lon = alt = heading = gs = bat_pct = bat_v = None
        gps_fix = gps_sats = None
        armed = False
        mode = None

        if v is not None:
            try:
                loc = relative_location(v)
                if loc is not None:
                    lat, lon, alt = loc.lat, loc.lon, loc.alt
                heading = float(v.heading) if v.heading is not None else None
                gs = float(v.groundspeed) if v.groundspeed is not None else None
                if v.battery is not None:
                    bat_pct = v.battery.level
                    bat_v = v.battery.voltage
                if v.gps_0 is not None:
                    gps_fix = v.gps_0.fix_type
                    gps_sats = v.gps_0.satellites_visible
                armed = bool(v.armed)
                mode = v.mode.name if v.mode is not None else None
            except Exception:
                pass

        return TelemetrySnapshot(
            state=state.value,
            mission_id=current.mission_id if current else None,
            lat=lat, lon=lon, alt_m=alt,
            heading_deg=heading,
            ground_speed_ms=gs,
            battery_pct=bat_pct,
            battery_voltage=bat_v,
            gps_fix=gps_fix,
            gps_sats=gps_sats,
            armed=armed,
            mode=mode,
            home_lat=self.config.home_lat,
            home_lon=self.config.home_lon,
            target_lat=current.target_lat if current else None,
            target_lon=current.target_lon if current else None,
            path=path,
            log_tail=log_tail,
        )

    # ---------- vehicle lifecycle ----------
    def ensure_connected(self) -> None:
        # Serialise connects: the API's eager-connect task and the first queued
        # mission can race here; without this lock both would dial SITL and one
        # Vehicle handle would leak.
        with self._connect_lock:
            if self.vehicle is not None:
                return
            with self._lock:
                no_mission = self._current is None
            if no_mission:
                self._set_state(MissionState.CONNECTING)
            self.vehicle = connect_vehicle(
                self.config.mavlink_connection,
                timeout_s=self.config.connect_timeout_s,
                retries=self.config.connect_retries,
            )
            self._log(f"vehicle connected on {self.config.mavlink_connection}")
            self._start_telemetry_recorder()
            # If we connected eagerly (no active mission), park state at IDLE so
            # external observers see we're ready, not still "connecting".
            with self._lock:
                if self._current is None and self._state == MissionState.CONNECTING:
                    self._set_state(MissionState.IDLE)

    def close(self) -> None:
        self._stop_telemetry.set()
        if self._telemetry_thread is not None:
            self._telemetry_thread.join(timeout=2.0)
        # Hold the connect lock so a close racing an in-flight ensure_connected
        # can't null the handle mid-connect.
        with self._connect_lock:
            if self.vehicle is not None:
                try:
                    self.vehicle.close()
                except Exception:
                    pass
                self.vehicle = None

    def shutdown_safe(self) -> None:
        """Called on API shutdown. If the vehicle is still airborne, send it
        home (confirmed RTL) before dropping the connection — never abandon
        an armed aircraft mid-mission."""
        v = self.vehicle
        try:
            if v is not None and bool(v.armed):
                self._log("shutdown with armed vehicle — commanding RTL before disconnect")
                self.request_abort("api shutdown")
                self._set_mode_confirmed("RTL", timeout_s=10)
        except Exception as exc:
            self._log(f"shutdown RTL attempt failed: {exc}")
        self.close()

    def _start_telemetry_recorder(self) -> None:
        if self._telemetry_thread is not None and self._telemetry_thread.is_alive():
            return
        self._stop_telemetry.clear()

        def _record() -> None:
            interval = max(0.1, self.config.telemetry_interval_ms / 1000.0)
            while not self._stop_telemetry.is_set():
                try:
                    if self.vehicle is not None:
                        loc = relative_location(self.vehicle)
                        if loc is not None:
                            with self._lock:
                                self._path.append({"lat": loc.lat, "lon": loc.lon, "alt": float(loc.alt or 0.0)})
                                if len(self._path) > 2000:
                                    self._path = self._path[-2000:]
                except Exception:
                    pass
                time.sleep(interval)

        self._telemetry_thread = threading.Thread(target=_record, name="telemetry-recorder", daemon=True)
        self._telemetry_thread.start()

    # ---------- mission phases ----------
    def _should_abort(self, failsafe: Optional[FailsafeHandler]) -> bool:
        if self._abort_requested.is_set():
            return True
        return failsafe is not None and failsafe.triggered

    def run_mission(self, spec: MissionSpec) -> MissionState:
        with self._lock:
            self._current = spec
            self._path.clear()
        self._abort_requested.clear()
        self._abort_reason = ""
        self._log(f"=== START mission {spec.mission_id} target=({spec.target_lat:.6f},{spec.target_lon:.6f}) alt={spec.altitude_m}m hover={spec.hover_s}s ===")
        started_at = time.time()
        failsafe: Optional[FailsafeHandler] = None
        try:
            self.ensure_connected()
            self._wait_until_safe_to_start()

            self._set_state(MissionState.WAITING_GPS)
            if not wait_for_gps_lock(self.vehicle, min_sats=6, timeout_s=60):
                raise RuntimeError("GPS lock not acquired")

            failsafe = FailsafeHandler(self.vehicle, self.config, started_at)
            failsafe.start()

            self._arm_and_takeoff(spec.altitude_m, failsafe)
            if self._should_abort(failsafe):
                return self._abort(failsafe)

            self._set_state(MissionState.ENROUTE)
            self._goto_avoiding(spec.target_lat, spec.target_lon, spec.altitude_m, failsafe)
            if self._should_abort(failsafe):
                return self._abort(failsafe)

            # honour any extra waypoints injected before/during enroute
            self._drain_extra_waypoints(spec.altitude_m, failsafe)
            if self._should_abort(failsafe):
                return self._abort(failsafe)

            # Hover for the full requested duration. Waypoints injected during
            # the hover interrupt it; the remaining hover time resumes after
            # the detour instead of being silently dropped. The hover window
            # doubles as the evidence-recording window (no-op without camera).
            self._set_state(MissionState.HOVERING)
            try:
                self.recorder.start(spec.mission_id)
            except Exception:
                pass
            remaining = float(spec.hover_s)
            while remaining > 0:
                remaining = self._hover(remaining, failsafe)
                if self._should_abort(failsafe):
                    return self._abort(failsafe)
                if remaining > 0:
                    self._drain_extra_waypoints(spec.altitude_m, failsafe)
                    if self._should_abort(failsafe):
                        return self._abort(failsafe)
                    self._set_state(MissionState.HOVERING)

            # First-aid kit drop (VanniKawachh response payload)
            if spec.deliver_kit:
                self._deliver_kit(spec, failsafe)
                if self._should_abort(failsafe):
                    return self._abort(failsafe)

            self._set_state(MissionState.RTL)
            self._rtl_and_wait_landed(failsafe)

            self._set_state(MissionState.COMPLETED)
            self._log(f"=== END mission {spec.mission_id} OK ===")
            return MissionState.COMPLETED

        except Exception as exc:
            self._log(f"mission failed: {exc}")
            self._set_state(MissionState.FAILED)
            self._safe_rtl()
            return MissionState.FAILED
        finally:
            try:
                self.recorder.stop()
            except Exception:
                pass
            if failsafe is not None:
                failsafe.stop()

    def _wait_until_safe_to_start(self) -> None:
        """Refuse to fly a new mission against a vehicle that is still armed
        (e.g. the previous mission aborted and is still descending)."""
        v = self.vehicle
        if not bool(v.armed):
            return
        self._log("vehicle still armed from a previous flight — waiting for disarm before new mission")
        deadline = time.time() + self.PREFLIGHT_DISARM_WAIT_S
        while time.time() < deadline:
            if not bool(v.armed):
                self._log("vehicle disarmed; safe to start")
                return
            time.sleep(1.0)
        raise RuntimeError(
            f"vehicle still armed after {self.PREFLIGHT_DISARM_WAIT_S}s — refusing to start a new mission"
        )

    def _arm_and_takeoff(self, target_alt_m: float, failsafe: FailsafeHandler) -> None:
        v = self.vehicle
        self._set_state(MissionState.ARMING)

        # SITL doesn't have an RC transmitter and ArduCopter 3.3 refuses to arm
        # under default pre-arm checks. We relax checks for the simulated drone.
        # On real hardware these would be left at their stock values.
        self._relax_sitl_arming_checks()

        # Wait for pre-arm. With ARMING_CHECK=0 this is fast.
        wait_until = time.time() + 45
        while not v.is_armable and time.time() < wait_until:
            self._log(f"waiting for pre-arm checks (armable={v.is_armable})...")
            if self._should_abort(failsafe):
                return
            time.sleep(1.0)
        if not v.is_armable:
            # Proceed anyway: dronekit's is_armable mirrors EKF flags that are
            # unreliable on Copter 3.3 SITL; a genuinely un-armable vehicle
            # will fail the explicit arm confirmation below.
            self._log("warning: is_armable still false after wait; attempting arm anyway")

        # Switch to GUIDED and confirm the autopilot accepted the change.
        if not self._set_mode_confirmed("GUIDED", timeout_s=10):
            raise RuntimeError(f"failed to enter GUIDED mode (current={v.mode.name})")

        # Arm and confirm.
        v.armed = True
        deadline = time.time() + 15
        while time.time() < deadline:
            if v.armed:
                break
            if self._should_abort(failsafe):
                return
            time.sleep(0.2)
        if not v.armed:
            raise RuntimeError("vehicle failed to arm")
        self._log(f"ARMED (mode={v.mode.name})")

        self._set_state(MissionState.TAKEOFF)
        v.simple_takeoff(target_alt_m)
        # Wait until we reach ~95% of target altitude
        climb_deadline = time.time() + 60
        while True:
            if self._should_abort(failsafe):
                return
            loc = relative_location(v)
            alt = loc.alt if loc is not None else 0.0
            self._log(f"climbing: alt={alt:.1f}m / {target_alt_m}m mode={v.mode.name} armed={v.armed}")
            if alt is not None and alt >= target_alt_m * 0.95:
                self._log(f"takeoff complete: alt={alt:.1f}m")
                return
            if time.time() > climb_deadline:
                raise RuntimeError(f"takeoff stalled at {alt:.1f}m / {target_alt_m}m (mode={v.mode.name})")
            time.sleep(1.0)

    def _relax_sitl_arming_checks(self) -> None:
        """For SITL only: disable pre-arm checks and RC failsafes.

        Gated by SITL_MODE=1. On real hardware we leave the ArduPilot stock
        pre-arm gating in force — disabling it on a real aircraft is unsafe.
        """
        if os.environ.get("SITL_MODE", "0") != "1":
            self._log("real-hardware mode: leaving ArduPilot pre-arm checks at stock values")
            return
        v = self.vehicle
        try:
            v.parameters["ARMING_CHECK"] = 0
            v.parameters["FS_THR_ENABLE"] = 0  # ignore missing RC throttle
            v.parameters["GPS_HDOP_GOOD"] = 100.0  # be lenient on HDOP
            self._log("SITL arming checks relaxed (ARMING_CHECK=0)")
        except Exception as exc:
            self._log(f"warning: could not set SITL params: {exc}")

    def _set_mode_confirmed(self, mode_name: str, timeout_s: float = 10.0) -> bool:
        """Set a flight mode and wait until the autopilot reports it.

        ArduCopter 3.3 (which dronekit-sitl ships on Windows) silently rejects
        dronekit's high-level mode setter under some conditions. We try the
        dronekit setter first, then fall back to a raw MAVLink COMMAND_LONG
        with MAV_CMD_DO_SET_MODE, and finally to the SET_MODE message.
        """
        v = self.vehicle
        target = self._mode(mode_name)
        # Attempt 1: dronekit high-level setter
        try:
            v.mode = target
        except Exception as exc:
            self._log(f"dronekit mode setter raised: {exc}")

        deadline = time.time() + timeout_s
        last_raw_send = 0.0
        attempts = 0
        while time.time() < deadline:
            if v.mode is not None and v.mode.name == mode_name:
                self._log(f"mode confirmed: {mode_name} (after {attempts} retries)")
                return True
            now = time.time()
            if now - last_raw_send >= 0.7:
                self._raw_set_mode(mode_name)
                last_raw_send = now
                attempts += 1
                # Also re-poke dronekit's setter — cheap.
                try:
                    v.mode = target
                except Exception:
                    pass
            time.sleep(0.2)
        self._log(f"mode change to {mode_name} not confirmed (current={v.mode.name if v.mode else '?'}, raw attempts={attempts})")
        return False

    def _raw_set_mode(self, mode_name: str) -> None:
        """Send raw MAVLink mode-set commands, bypassing dronekit's setter."""
        from pymavlink import mavutil
        v = self.vehicle
        try:
            master = v._master
            mapping = master.mode_mapping() or {}
            if mode_name not in mapping:
                return
            mode_id = mapping[mode_name]
            base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            # 1) COMMAND_LONG / DO_SET_MODE — most reliable on older Copter
            master.mav.command_long_send(
                master.target_system, master.target_component,
                mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
                base_mode, mode_id, 0, 0, 0, 0, 0,
            )
            # 2) SET_MODE message — secondary path
            master.mav.set_mode_send(master.target_system, base_mode, mode_id)
        except Exception as exc:
            self._log(f"raw mode-set failed: {exc}")

    def _goto_avoiding(self, lat: float, lon: float, alt: float, failsafe: FailsafeHandler) -> None:
        """Fly to (lat, lon) routing around configured keep-out zones.

        Map-based avoidance only: re-plans the horizontal path around known
        obstacles. With none configured this is exactly a direct goto, so the
        nominal mission is unchanged. (Sensor-based reactive avoidance is a
        separate, hardware-dependent roadmap item — not done here.)
        """
        if not self.obstacles:
            return self._goto_waypoint(lat, lon, alt, failsafe)
        loc = relative_location(self.vehicle)
        if loc is None or loc.lat is None:
            return self._goto_waypoint(lat, lon, alt, failsafe)
        route = plan_route((loc.lat, loc.lon), (lat, lon),
                           self.obstacles, self.config.obstacle_clearance_m)
        if len(route) > 1:
            self._log(f"obstacle avoidance: routing around keep-out zone(s) via "
                      f"{len(route) - 1} detour waypoint(s)")
        for wlat, wlon in route:
            if self._should_abort(failsafe):
                return
            if (wlat, wlon) != (lat, lon):
                self._log(f"avoidance waypoint -> ({wlat:.6f},{wlon:.6f})")
            self._goto_waypoint(wlat, wlon, alt, failsafe)

    def _goto_waypoint(self, lat: float, lon: float, alt: float, failsafe: FailsafeHandler) -> None:
        v = self.vehicle
        target = LocationGlobalRelative(lat, lon, alt)
        v.simple_goto(target, groundspeed=self.config.cruise_speed_ms)
        tol = self.config.waypoint_tolerance_m
        # Stall detection: if closest-approach hasn't improved by >2 m within
        # leg_stall_timeout_s, the leg is stuck (wind, mode flip, bad command)
        # — fail the mission rather than burn battery until the global timeout.
        best_dist = float("inf")
        last_progress_at = time.time()
        while True:
            if self._should_abort(failsafe):
                return
            loc = relative_location(v)
            if loc is None:
                time.sleep(0.5)
                continue
            d = haversine_distance_m(loc.lat, loc.lon, lat, lon)
            self._log(f"enroute: dist_to_target={d:.1f}m alt={loc.alt:.1f}m")
            if d <= tol:
                self._log(f"reached waypoint within {d:.1f}m (tol={tol}m)")
                return
            if d < best_dist - 2.0:
                best_dist = d
                last_progress_at = time.time()
            elif time.time() - last_progress_at > self.config.leg_stall_timeout_s:
                raise RuntimeError(
                    f"leg stalled: no progress for {self.config.leg_stall_timeout_s:.0f}s "
                    f"(dist={d:.1f}m, best={best_dist:.1f}m)"
                )
            time.sleep(1.0)

    def _drain_extra_waypoints(self, default_alt: float, failsafe: FailsafeHandler) -> None:
        while True:
            with self._lock:
                if not self._extra_waypoints_pending:
                    return
                wp = self._extra_waypoints_pending.pop(0)
            self._log(f"flying to extra waypoint ({wp.lat:.6f},{wp.lon:.6f})")
            alt = wp.alt if wp.alt is not None else default_alt
            self._goto_avoiding(wp.lat, wp.lon, alt, failsafe)
            if self._should_abort(failsafe):
                return

    def _hover(self, seconds: float, failsafe: FailsafeHandler) -> float:
        """Hover for up to ``seconds``. Returns the unhovered remainder —
        0.0 when the full duration completed, >0 when interrupted by an
        injected waypoint (the caller flies the detour and resumes)."""
        self._log(f"hovering for {seconds:.0f}s")
        end = time.time() + seconds
        while time.time() < end:
            if self._should_abort(failsafe):
                return 0.0
            with self._lock:
                if self._extra_waypoints_pending:
                    remaining = max(0.0, end - time.time())
                    self._log(f"hover interrupted by waypoint ({remaining:.0f}s remaining)")
                    return remaining
            time.sleep(0.5)
        return 0.0

    def _deliver_kit(self, spec: MissionSpec, failsafe: FailsafeHandler) -> None:
        """DELIVERING phase: descend to the drop altitude over the incident
        point, release the first-aid kit, and climb back to cruise altitude.

        A failed release is reported but never blocks the mission — the drone
        proceeds to RTL either way (never loiter on a failed drop)."""
        v = self.vehicle
        self._set_state(MissionState.DELIVERING)
        drop_alt = self.config.payload_drop_alt_m
        loc = relative_location(v)
        if loc is None:
            self._log("delivery skipped: no position fix")
            return
        self._log(f"descending to {drop_alt:.1f}m for kit drop")
        v.simple_goto(LocationGlobalRelative(loc.lat, loc.lon, drop_alt))
        deadline = time.time() + 45
        while time.time() < deadline:
            if self._should_abort(failsafe):
                return
            cur = relative_location(v)
            if cur is not None and cur.alt is not None and abs(cur.alt - drop_alt) <= 0.7:
                break
            time.sleep(0.5)
        else:
            self._log("warning: drop-altitude descent timed out — dropping from current altitude")
        ok = release_kit(
            v,
            channel=self.config.payload_servo_channel,
            open_pwm=self.config.payload_open_pwm,
            hold_pwm=self.config.payload_hold_pwm,
        )
        self._log("first-aid kit " + ("RELEASED" if ok else "RELEASE FAILED — continuing to RTL"))
        # climb back to cruise altitude before RTL so the return is clean
        v.simple_goto(LocationGlobalRelative(loc.lat, loc.lon, spec.altitude_m))
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._should_abort(failsafe):
                return
            cur = relative_location(v)
            if cur is not None and cur.alt is not None and cur.alt >= spec.altitude_m * 0.9:
                break
            time.sleep(0.5)

    def _rtl_and_wait_landed(self, failsafe: Optional[FailsafeHandler]) -> None:
        v = self.vehicle
        self._set_mode_confirmed("RTL", timeout_s=10)
        deadline = time.time() + 240  # cap RTL phase so we never hang
        while time.time() < deadline:
            # Honour failsafe escalation mid-RTL: a critical-battery or
            # GPS-loss LAND demand overrides continuing home.
            if failsafe is not None and failsafe.triggered and failsafe.required_action == "LAND":
                if v.mode is None or v.mode.name != "LAND":
                    self._log("failsafe demands LAND during RTL — switching to LAND")
                    self._set_mode_confirmed("LAND", timeout_s=10)
            loc = relative_location(v)
            alt = loc.alt if loc is not None else 0.0
            armed = bool(v.armed)
            self._log(f"RTL: alt={alt:.1f}m armed={armed} mode={v.mode.name}")
            if not armed and alt is not None and alt < 0.5:
                self._set_state(MissionState.LANDED)
                self._log("LANDED")
                return
            time.sleep(1.0)
        # If RTL stalls, force LAND.
        self._log("RTL timeout — issuing LAND")
        self._set_mode_confirmed("LAND", timeout_s=10)
        for _ in range(120):
            loc = relative_location(v)
            alt = loc.alt if loc is not None else 0.0
            if not v.armed and alt < 0.5:
                self._set_state(MissionState.LANDED)
                self._log("LANDED (via LAND fallback)")
                return
            time.sleep(1.0)
        self._log("warning: vehicle never confirmed landed")
        self._set_state(MissionState.LANDED)

    def _abort(self, failsafe: Optional[FailsafeHandler]) -> MissionState:
        """Abort the mission: command the failsafe action with the confirmed
        mode setter, then BLOCK until the vehicle lands and disarms (or the
        hard timeout passes). Returning early here would let the queue start
        the next mission against an airborne vehicle."""
        self._set_state(MissionState.ABORTED)
        if failsafe is not None and failsafe.triggered:
            action = failsafe.required_action if failsafe.required_action in ("RTL", "LAND") else "RTL"
            why = "failsafe"
        else:
            action = "RTL"
            why = self._abort_reason or "operator cancel"
        self._log(f"aborting mission ({why}), action={action}")
        if not self._set_mode_confirmed(action, timeout_s=self.ABORT_MODE_TIMEOUT_S):
            # Last resort: if the requested action won't confirm, try the other.
            fallback = "LAND" if action == "RTL" else "RTL"
            self._log(f"abort mode {action} not confirmed — trying {fallback}")
            self._set_mode_confirmed(fallback, timeout_s=self.ABORT_MODE_TIMEOUT_S)
        self._wait_for_disarm(self.ABORT_LAND_WAIT_S)
        return MissionState.ABORTED

    def _safe_rtl(self) -> None:
        """Recovery path for unexpected mission exceptions: send the vehicle
        home with the confirmed setter and wait for it to come down."""
        if self.vehicle is None:
            return
        try:
            if not bool(self.vehicle.armed):
                return  # on the ground; nothing to recover
            self._log("mission error with vehicle airborne — commanding RTL")
            if not self._set_mode_confirmed("RTL", timeout_s=self.ABORT_MODE_TIMEOUT_S):
                self._set_mode_confirmed("LAND", timeout_s=self.ABORT_MODE_TIMEOUT_S)
            self._wait_for_disarm(self.ABORT_LAND_WAIT_S)
        except Exception as exc:
            self._log(f"safe-RTL recovery failed: {exc}")

    def _wait_for_disarm(self, timeout_s: float) -> bool:
        v = self.vehicle
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                loc = relative_location(v)
                alt = loc.alt if loc is not None else None
                if not bool(v.armed):
                    self._log(f"vehicle disarmed (alt={alt if alt is not None else '?'})")
                    return True
            except Exception:
                pass
            time.sleep(1.0)
        self._log(f"warning: vehicle still armed after {timeout_s:.0f}s abort wait")
        return False

    def _mode(self, name: str):
        from dronekit import VehicleMode
        return VehicleMode(name)
