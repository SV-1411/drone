"""Optional SIMNET/ArduPilot MAVLink bridge.

The deployed hub can drive a SIMNET ArduPilot SITL session when SIMNET_HOST and
SIMNET_PORT are configured. The browser/Render app remains the mission source;
SIMNET becomes the actual flight-physics and 3D-environment engine.

This module deliberately does nothing when the session endpoint is not
configured, so normal Render startup remains safe.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    from pymavlink import mavutil
except Exception:  # pragma: no cover - optional dependency
    mavutil = None

log = logging.getLogger("simnet.bridge")


@dataclass
class SimnetState:
    connected: bool = False
    state: str = "DISCONNECTED"
    mission_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    altitude_m: float = 0.0
    speed_ms: float = 0.0
    heading_deg: float = 0.0
    battery_pct: Optional[float] = None
    armed: bool = False
    mode: str = ""
    target_lat: Optional[float] = None
    target_lon: Optional[float] = None
    kit_dropped: bool = False
    last_heartbeat: float = 0.0


class SimnetMavlinkBridge:
    """Thin MAVLink adapter for a SIMNET ArduPilot SITL session.

    SIMNET exposes the current session TCP host/port in its Ground Control
    Station panel. Once those are placed in the environment, this bridge can
    arm, take off, navigate, command payload release, and RTL the ArduPilot
    vehicle. Telemetry is continuously cached for the VanniKawachh API/UI.
    """

    def __init__(self) -> None:
        self.host = os.environ.get("SIMNET_HOST", "").strip()
        self.port = int(os.environ.get("SIMNET_PORT", "0") or 0)
        self.payload_servo = int(os.environ.get("SIMNET_PAYLOAD_SERVO", "9") or 9)
        self.payload_pwm = int(os.environ.get("SIMNET_PAYLOAD_PWM", "1900") or 1900)
        self.takeoff_alt_m = float(os.environ.get("SIMNET_TAKEOFF_ALT_M", "15") or 15)
        self.state = SimnetState()
        self._lock = threading.RLock()
        self._conn = None
        self._reader: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_target = None

    @property
    def configured(self) -> bool:
        return bool(self.host and self.port and mavutil is not None)

    def connect(self) -> bool:
        if not self.configured:
            return False
        with self._lock:
            if self._conn is not None:
                return True
        try:
            conn = mavutil.mavlink_connection(f"tcp:{self.host}:{self.port}")
            conn.wait_heartbeat(timeout=12)
            with self._lock:
                self._conn = conn
                self.state.connected = True
                self.state.state = "CONNECTED"
                self.state.last_heartbeat = time.time()
            self._stop.clear()
            self._reader = threading.Thread(target=self._read_loop, daemon=True, name="simnet-mavlink")
            self._reader.start()
            log.info("Connected to SIMNET SITL at tcp:%s:%s", self.host, self.port)
            return True
        except Exception as exc:
            log.warning("SIMNET connection failed: %s", exc)
            with self._lock:
                self._conn = None
                self.state.connected = False
                self.state.state = "DISCONNECTED"
            return False

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            conn = self._conn
            self._conn = None
            self.state.connected = False
            self.state.state = "DISCONNECTED"
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            conn = self._conn
            if conn is None:
                time.sleep(0.2)
                continue
            try:
                msg = conn.recv_match(blocking=True, timeout=1.0)
            except Exception:
                continue
            if msg is None:
                continue
            typ = msg.get_type()
            try:
                with self._lock:
                    self.state.last_heartbeat = time.time()
                    if typ == "HEARTBEAT":
                        self.state.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                        try:
                            self.state.mode = mavutil.mode_string_v10(msg)
                        except Exception:
                            self.state.mode = ""
                    elif typ == "GLOBAL_POSITION_INT":
                        self.state.lat = msg.lat / 1e7
                        self.state.lon = msg.lon / 1e7
                        self.state.altitude_m = msg.relative_alt / 1000.0
                        self.state.speed_ms = ((msg.vx ** 2 + msg.vy ** 2) ** 0.5) / 100.0
                        self.state.heading_deg = msg.hdg / 100.0 if msg.hdg != 65535 else self.state.heading_deg
                    elif typ == "VFR_HUD":
                        self.state.speed_ms = float(msg.groundspeed)
                        self.state.altitude_m = float(msg.alt)
                        self.state.heading_deg = float(msg.heading)
                    elif typ == "SYS_STATUS":
                        self.state.battery_pct = float(msg.battery_remaining) if msg.battery_remaining >= 0 else None
            except Exception:
                continue

    def _command_long(self, command: int, params) -> None:
        with self._lock:
            conn = self._conn
        if conn is None:
            raise RuntimeError("SIMNET not connected")
        conn.mav.command_long_send(
            conn.target_system,
            conn.target_component,
            command,
            0,
            *params,
        )

    def set_mode_guided(self) -> None:
        with self._lock:
            conn = self._conn
        if conn is None:
            raise RuntimeError("SIMNET not connected")
        mode = conn.mode_mapping().get("GUIDED")
        if mode is None:
            raise RuntimeError("GUIDED mode unavailable")
        conn.mav.set_mode_send(conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode)

    def arm(self) -> None:
        self._command_long(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, [1, 0, 0, 0, 0, 0, 0])

    def takeoff(self, altitude_m: Optional[float] = None) -> None:
        self.set_mode_guided()
        self.arm()
        self._command_long(
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            [0, 0, 0, 0, 0, 0, float(altitude_m or self.takeoff_alt_m)],
        )

    def goto(self, lat: float, lon: float, alt_m: float) -> None:
        with self._lock:
            conn = self._conn
        if conn is None:
            raise RuntimeError("SIMNET not connected")
        self.set_mode_guided()
        # Ignore velocity/acceleration/yaw fields. Keep only position active.
        type_mask = 0b0000111111111000
        conn.mav.set_position_target_global_int_send(
            0,
            conn.target_system,
            conn.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            type_mask,
            int(lat * 1e7),
            int(lon * 1e7),
            float(alt_m),
            0, 0, 0, 0, 0, 0, 0, 0,
        )
        with self._lock:
            self._last_target = (float(lat), float(lon), float(alt_m))
            self.state.target_lat = float(lat)
            self.state.target_lon = float(lon)

    def drop_payload(self) -> None:
        self._command_long(
            mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
            [self.payload_servo, self.payload_pwm, 0, 0, 0, 0, 0],
        )
        with self._lock:
            self.state.kit_dropped = True

    def rtl(self) -> None:
        with self._lock:
            conn = self._conn
        if conn is None:
            raise RuntimeError("SIMNET not connected")
        mode = conn.mode_mapping().get("RTL")
        if mode is None:
            raise RuntimeError("RTL mode unavailable")
        conn.mav.set_mode_send(conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode)

    def mission(self, mission_id: str, target_lat: float, target_lon: float, hover_s: int = 3) -> bool:
        if not self.connect():
            return False
        with self._lock:
            self.state.mission_id = mission_id
            self.state.state = "ARMING"
            self.state.kit_dropped = False
        try:
            self.takeoff(self.takeoff_alt_m)
            with self._lock:
                self.state.state = "TAKEOFF"
            time.sleep(1.5)
            self.goto(target_lat, target_lon, self.takeoff_alt_m)
            with self._lock:
                self.state.state = "ENROUTE"
            # Navigation is performed by ArduPilot/SIMNET. Wait until the
            # vehicle is close to the target while keeping the bridge responsive.
            deadline = time.time() + max(60.0, self._distance_time_budget(target_lat, target_lon))
            while time.time() < deadline and not self._stop.is_set():
                with self._lock:
                    lat, lon = self.state.lat, self.state.lon
                if lat is not None and lon is not None and _haversine(lat, lon, target_lat, target_lon) <= 8.0:
                    break
                time.sleep(0.5)
            with self._lock:
                self.state.state = "HOVERING"
            time.sleep(max(1, int(hover_s)))
            with self._lock:
                self.state.state = "DELIVERING"
            self.drop_payload()
            time.sleep(1.0)
            self.rtl()
            with self._lock:
                self.state.state = "RTL"
            return True
        except Exception as exc:
            log.exception("SIMNET mission failed: %s", exc)
            with self._lock:
                self.state.state = "FAILED"
            return False

    def _distance_time_budget(self, target_lat: float, target_lon: float) -> float:
        with self._lock:
            lat, lon = self.state.lat, self.state.lon
        if lat is None or lon is None:
            return 300.0
        return _haversine(lat, lon, target_lat, target_lon) / 12.0 + 30.0

    def snapshot(self) -> dict:
        with self._lock:
            s = self.state
            return {
                "source": "simnet",
                "connected": s.connected,
                "state": s.state,
                "mission_id": s.mission_id,
                "lat": s.lat,
                "lon": s.lon,
                "altitude_m": s.altitude_m,
                "speed_ms": s.speed_ms,
                "ground_speed_ms": s.speed_ms,
                "heading_deg": s.heading_deg,
                "battery_pct": s.battery_pct,
                "armed": s.armed,
                "mode": s.mode,
                "target": [s.target_lat, s.target_lon] if s.target_lat is not None else None,
                "kit_dropped": s.kit_dropped,
                "motor_rpm": 0,
                "simnet_host_configured": self.configured,
                "last_heartbeat_age_s": max(0.0, time.time() - s.last_heartbeat) if s.last_heartbeat else None,
            }


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import radians, sin, cos, asin, sqrt
    R = 6_371_000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))
