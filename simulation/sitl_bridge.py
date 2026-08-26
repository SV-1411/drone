#!/usr/bin/env python3
"""Bridge the deployed VanniKawachh mission trigger to ArduPilot SITL.

Run this only in the actual simulation environment where ArduPilot SITL and
pymavlink are available. It polls the deployed hub for a new mission and drives
ArduCopter in GUIDED mode, then performs hover/payload/RTL steps.

This intentionally does not replace the hub or the browser UI. It is the
physics adapter between the deployed mission event and a real SITL/Gazebo
vehicle.
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


def dist_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


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
    conn.arducopter_arm()
    conn.motors_armed_wait()
    print("[SITL] armed")


def takeoff(conn, altitude_m: float):
    conn.mav.command_long_send(
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0, 0, 0, 0, 0, 0,
        altitude_m,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
        if msg and msg.relative_alt >= altitude_m * 1000 * 0.85:
            print(f"[SITL] takeoff reached ~{msg.relative_alt/1000:.1f} m")
            return
    raise RuntimeError("Timed out during takeoff")


def goto(conn, lat: float, lon: float, alt: float):
    mask = 0b110111111000  # position only: ignore velocity/accel/yaw fields
    conn.mav.set_position_target_global_int_send(
        int(time.time() * 1000) & 0xFFFFFFFF,
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        mask,
        int(lat * 1e7),
        int(lon * 1e7),
        alt,
        0, 0, 0,
        0, 0, 0,
        0, 0,
    )


def wait_target(conn, lat: float, lon: float, radius_m: float = 3.0):
    deadline = time.time() + max(60.0, dist_m(current_position(conn), (lat, lon)) / 2.0 + 60)
    while time.time() < deadline:
        pos = current_position(conn)
        d = dist_m(pos, (lat, lon))
        print(f"[SITL] target distance={d:.1f} m", end="\r")
        if d <= radius_m:
            print()
            return
        time.sleep(0.5)
    raise RuntimeError("Timed out reaching target")


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


def rtl_and_land(conn):
    set_mode(conn, "RTL")
    deadline = time.time() + 180
    while time.time() < deadline:
        hb = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb and not (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            print("[SITL] vehicle disarmed after RTL")
            return
    raise RuntimeError("RTL did not complete before timeout")


def report_to_hub(lat: float, lon: float, state: str, kit: Optional[int] = None):
    params = {"lat": lat, "lon": lon, "state": state}
    if kit is not None:
        params["kit"] = kit
    try:
        requests.post(f"{HUB_URL}/drone-report", params=params, timeout=5)
    except Exception as exc:
        print(f"[HUB] report failed: {exc}")


def mission_from_hub() -> Optional[dict]:
    try:
        r = requests.get(f"{HUB_URL}/drone_state", params={"ts": time.time()}, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"[HUB] poll failed: {exc}")
        return None


def run_mission(conn, d: dict):
    target = tuple(d["target"])
    print(f"[MISSION] {d.get('mission_id')} -> {target}")
    set_mode(conn, "GUIDED")
    arm(conn)
    report_to_hub(*current_position(conn), "ARMING")

    takeoff(conn, CRUISE_ALT_M)
    report_to_hub(*current_position(conn), "TAKEOFF")

    goto(conn, target[0], target[1], CRUISE_ALT_M)
    while True:
        pos = current_position(conn)
        report_to_hub(pos[0], pos[1], "ENROUTE")
        if dist_m(pos, target) <= 3.0:
            break
        time.sleep(0.5)

    report_to_hub(target[0], target[1], "HOVERING", 0)
    time.sleep(HOVER_S)
    report_to_hub(target[0], target[1], "DELIVERING", 0)
    set_payload(conn, SERVO_OPEN)
    time.sleep(1.5)
    report_to_hub(target[0], target[1], "DELIVERING", 1)
    time.sleep(1.0)
    set_payload(conn, SERVO_CLOSED)

    rtl_and_land(conn)
    report_to_hub(*current_position(conn), "COMPLETED", 1)
    print("[MISSION] complete")


def main():
    conn = mavutil.mavlink_connection(MAVLINK)
    wait_heartbeat(conn)
    last_mission = None
    while True:
        d = mission_from_hub()
        mid = d.get("mission_id") if d else None
        if d and mid and mid != last_mission and d.get("state") in {"ARMING", "TAKEOFF", "ENROUTE"} and d.get("target"):
            try:
                run_mission(conn, d)
                last_mission = mid
            except Exception as exc:
                print(f"[MISSION] FAILED: {exc}")
                try:
                    set_mode(conn, "RTL")
                except Exception:
                    pass
                last_mission = mid
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
