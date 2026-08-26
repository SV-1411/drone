#!/usr/bin/env python3
"""VanniKawachh <-> real ArduPilot SITL + Gazebo bridge.

Run this on the machine that runs Gazebo Harmonic and ArduCopter SITL. It polls
/incidents for newly dispatched VanniKawachh missions, commands ArduPilot over
MAVLink, and continuously reports real SITL telemetry to /sitl-report so the
Render GCS can visualize the physical simulation state.
"""
from __future__ import annotations

import math
import os
import time
from typing import Optional, Tuple

import requests
from pymavlink import mavutil

HUB_URL = os.environ.get("VANNIKAWACHH_HUB", "https://vannikawachh-hub.onrender.com").rstrip("/")
MAVLINK = os.environ.get("MAVLINK_CONNECTION", "udp:127.0.0.1:14550")
CRUISE_ALT_M = float(os.environ.get("DRONE_CRUISE_ALT_M", "15"))
HOVER_S = float(os.environ.get("DRONE_HOVER_S", "3"))
SERVO_CHANNEL = int(os.environ.get("PAYLOAD_SERVO_CHANNEL", "9"))
SERVO_OPEN = float(os.environ.get("PAYLOAD_SERVO_OPEN", "1900"))
SERVO_CLOSED = float(os.environ.get("PAYLOAD_SERVO_CLOSED", "1100"))
POLL_S = float(os.environ.get("HUB_POLL_S", "0.5"))
REPORT_S = float(os.environ.get("SITL_REPORT_S", "0.5"))

# MAVLink POSITION_TARGET type mask: ignore velocity, acceleration, yaw and yaw rate.
POSITION_ONLY_MASK = 0x0DF8


def dist_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(max(0.0, x)))


def wait_heartbeat(conn):
    print(f"[SITL] connecting: {MAVLINK}")
    conn.wait_heartbeat(timeout=30)
    print(f"[SITL] heartbeat system={conn.target_system} component={conn.target_component}")


def set_mode(conn, mode: str):
    mapping = conn.mode_mapping()
    if not mapping or mode not in mapping:
        raise RuntimeError(f"SITL does not expose mode {mode!r}; mapping={mapping}")
    conn.set_mode(mapping[mode])
    deadline = time.time() + 10
    while time.time() < deadline:
        msg = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if msg and mavutil.mode_string_v10(msg) == mode:
            print(f"[SITL] mode={mode}")
            return
    raise RuntimeError(f"Timed out waiting for mode {mode}")


def arm(conn):
    # Use the explicit MAVLink command and wait for the armed bit. This makes
    # pre-arm failures visible instead of blindly issuing takeoff.
    conn.mav.command_long_send(
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1, 0, 0, 0, 0, 0, 0,
    )
    deadline = time.time() + 20
    last_text = None
    while time.time() < deadline:
        msg = conn.recv_match(blocking=True, timeout=1)
        if not msg:
            continue
        mtype = msg.get_type()
        if mtype == "STATUSTEXT":
            last_text = str(getattr(msg, "text", ""))
            print(f"[SITL] {last_text}")
        elif mtype == "HEARTBEAT":
            if msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                print("[SITL] armed")
                return
    raise RuntimeError(f"ArduPilot did not arm within 20s. Last status: {last_text or 'none'}")


def takeoff(conn, altitude_m: float):
    conn.mav.command_long_send(
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0, 0, 0, 0, 0, 0,
        altitude_m,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
        if msg and msg.relative_alt >= altitude_m * 1000 * 0.85:
            print(f"[SITL] takeoff reached ~{msg.relative_alt / 1000:.1f} m")
            return
    raise RuntimeError("Timed out during takeoff")


def goto(conn, lat: float, lon: float, alt: float):
    conn.mav.set_position_target_global_int_send(
        int(time.time() * 1000) & 0xFFFFFFFF,
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        POSITION_ONLY_MASK,
        int(lat * 1e7),
        int(lon * 1e7),
        alt,
        0, 0, 0,
        0, 0, 0,
        0, 0,
    )


def read_telemetry(conn) -> dict:
    """Drain the latest common telemetry messages without blocking."""
    out = {}
    for _ in range(30):
        msg = conn.recv_match(blocking=False)
        if msg is None:
            break
        t = msg.get_type()
        if t == "GLOBAL_POSITION_INT":
            out.update({
                "lat": msg.lat / 1e7,
                "lon": msg.lon / 1e7,
                "altitude_m": msg.relative_alt / 1000.0,
                "ground_speed_ms": math.hypot(msg.vx, msg.vy) / 100.0,
                "vertical_speed_ms": -(msg.vz / 100.0),
                "heading_deg": (msg.hdg / 100.0) if msg.hdg != 65535 else 0.0,
            })
        elif t == "VFR_HUD":
            out.update({
                "ground_speed_ms": float(getattr(msg, "groundspeed", out.get("ground_speed_ms", 0.0))),
                "heading_deg": float(getattr(msg, "heading", out.get("heading_deg", 0.0))),
            })
        elif t == "SYS_STATUS":
            batt = getattr(msg, "battery_remaining", -1)
            if batt is not None and batt >= 0:
                out["battery_pct"] = float(batt)
        elif t == "HEARTBEAT":
            out["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            out["flight_mode"] = mavutil.mode_string_v10(msg)
        elif t == "SERVO_OUTPUT_RAW":
            pwm = [getattr(msg, f"servo{i}_raw", 0) for i in range(1, 5)]
            motor_cmd = max(pwm) if pwm else 0
            out["motors_active"] = any(p > 1120 for p in pwm)
            # This is a visual/control estimate, not a measured motor RPM.
            out["motor_rpm"] = max(0.0, min(5500.0, (motor_cmd - 1100) * 6.875))
    return out


def report_to_hub(mission_id: Optional[str], home: Optional[Tuple[float, float]], target: Optional[Tuple[float, float]],
                  state: str, kit: int, telemetry: dict):
    payload = {
        "mission_id": mission_id,
        "state": state,
        "kit_dropped": bool(kit),
        "source": "ARDUPILOT_SITL_GAZEBO",
        "target": list(target) if target else None,
        "home": list(home) if home else None,
        **telemetry,
    }
    try:
        requests.post(f"{HUB_URL}/sitl-report", json=payload, timeout=5)
    except Exception as exc:
        print(f"[HUB] telemetry report failed: {exc}")


def incidents_from_hub() -> list[dict]:
    try:
        r = requests.get(f"{HUB_URL}/incidents", params={"ts": time.time()}, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"[HUB] incident poll failed: {exc}")
        return []


def current_position(conn) -> Tuple[float, float]:
    msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
    if not msg:
        raise RuntimeError("No GLOBAL_POSITION_INT telemetry")
    return msg.lat / 1e7, msg.lon / 1e7


def set_payload(conn, pwm: float):
    conn.mav.command_long_send(
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
        0,
        SERVO_CHANNEL,
        pwm,
        0, 0, 0, 0, 0,
    )
    print(f"[SITL] payload servo channel={SERVO_CHANNEL} pwm={pwm}")


def rtl_and_land(conn, mission_id, home, target, kit, state_before="RTL"):
    set_mode(conn, "RTL")
    deadline = time.time() + 180
    while time.time() < deadline:
        telemetry = read_telemetry(conn)
        telemetry.setdefault("lat", home[0])
        telemetry.setdefault("lon", home[1])
        report_to_hub(mission_id, home, target, state_before, kit, telemetry)
        if telemetry.get("armed") is False:
            print("[SITL] vehicle disarmed after RTL")
            return
        time.sleep(REPORT_S)
    raise RuntimeError("RTL did not complete before timeout")


def run_mission(conn, incident: dict):
    mission_id = incident.get("mission_id") or f"sitl-{int(time.time())}"
    target = (float(incident["lat"]), float(incident["lon"]))
    home = current_position(conn)
    kit = 0
    print(f"[MISSION] {mission_id} -> {target}")

    set_mode(conn, "GUIDED")
    arm(conn)
    telemetry = read_telemetry(conn)
    report_to_hub(mission_id, home, target, "ARMING", kit, telemetry)

    takeoff(conn, CRUISE_ALT_M)
    telemetry = read_telemetry(conn)
    report_to_hub(mission_id, home, target, "TAKEOFF", kit, telemetry)

    goto(conn, target[0], target[1], CRUISE_ALT_M)
    deadline = time.time() + max(180.0, dist_m(home, target) / 2.0 + 180.0)
    while time.time() < deadline:
        telemetry = read_telemetry(conn)
        if "lat" not in telemetry:
            time.sleep(REPORT_S)
            continue
        d = dist_m((telemetry["lat"], telemetry["lon"]), target)
        report_to_hub(mission_id, home, target, "ENROUTE", kit, telemetry)
        if d <= 5.0:
            break
        time.sleep(REPORT_S)
    else:
        raise RuntimeError("Timed out reaching distress target")

    telemetry = read_telemetry(conn)
    report_to_hub(mission_id, home, target, "HOVERING", kit, telemetry)
    time.sleep(HOVER_S)

    report_to_hub(mission_id, home, target, "DELIVERING", kit, telemetry)
    set_payload(conn, SERVO_OPEN)
    time.sleep(1.5)
    kit = 1
    telemetry = read_telemetry(conn)
    report_to_hub(mission_id, home, target, "DELIVERING", kit, telemetry)
    time.sleep(1.0)
    set_payload(conn, SERVO_CLOSED)

    rtl_and_land(conn, mission_id, home, target, kit)
    telemetry = read_telemetry(conn)
    report_to_hub(mission_id, home, target, "COMPLETED", kit, telemetry)
    print("[MISSION] complete")


def main():
    conn = mavutil.mavlink_connection(MAVLINK)
    wait_heartbeat(conn)
    last_mission = None
    print(f"[SITL] watching {HUB_URL}/incidents")
    while True:
        incidents = incidents_from_hub()
        incident = next((i for i in reversed(incidents)
                         if i.get("dispatched") and i.get("mission_id") and i.get("lat") is not None), None)
        mid = incident.get("mission_id") if incident else None
        if incident and mid and mid != last_mission:
            try:
                run_mission(conn, incident)
            except Exception as exc:
                print(f"[MISSION] FAILED: {exc}")
                try:
                    set_mode(conn, "RTL")
                except Exception:
                    pass
            finally:
                last_mission = mid
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
