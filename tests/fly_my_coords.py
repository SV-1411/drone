"""One-off demo: fly from MY current (IP-geolocated) coordinates to a random
nearby target, in SITL, and report whether it works.

HOME  = Nagpur, Maharashtra (≈ your current location, IP-geolocated)
TARGET = a random point ~490 m north-east of home (well inside the 5 km geofence)

Spawns dronekit-sitl (home set to your coords) + the FastAPI trigger service,
posts the mission, watches telemetry until the drone reaches the target and
returns to land, then prints PASS/FAIL. No hardware, pure simulation.

Run from project root:
    .venv\\Scripts\\python.exe tests\\fly_my_coords.py
"""
from __future__ import annotations

import math
import os
import socket
import subprocess
import sys
import time
from typing import Optional, Tuple

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# --- MY coordinates (IP-geolocated: Nagpur, Maharashtra) ---
HOME_LAT, HOME_LON = 21.1463, 79.0849
HOME_ALT_M = 310                      # Nagpur ground elevation (approx)
# --- random nearby target: +0.0030 lat (~333 m N), +0.0035 lon (~363 m E) ---
TARGET_LAT, TARGET_LON = 21.1493, 79.0884
ALT_M = 20.0
HOVER_S = 6
TOLERANCE_M = 5.0
API_URL = "http://127.0.0.1:8000"
SITL_PORT = 5760
MISSION_TIMEOUT_S = 360


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _port_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for(name: str, fn, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(1.0)
    print(f"[fly] timeout waiting for: {name}")
    return False


def _kill_tree(p: Optional[subprocess.Popen], name: str) -> None:
    if p is None or p.poll() is not None:
        return
    print(f"[fly] terminating {name} (pid {p.pid})")
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else:
            p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    except Exception:
        pass


def _clear_stale_sitl() -> bool:
    if not _port_listening("127.0.0.1", SITL_PORT):
        return True
    print(f"[fly] WARNING: port {SITL_PORT} already in use — killing stale SITL")
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/IM", "apm.exe"], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", "apm"], capture_output=True)
    deadline = time.time() + 10
    while time.time() < deadline:
        if not _port_listening("127.0.0.1", SITL_PORT):
            print("[fly] stale SITL cleared")
            return True
        time.sleep(0.5)
    return False


def _start_sitl() -> subprocess.Popen:
    print(f"[fly] starting SITL at HOME {HOME_LAT},{HOME_LON} (Nagpur)")
    cmd = [sys.executable, "-m", "dronekit_sitl", "copter-3.3",
           f"--home={HOME_LAT},{HOME_LON},{HOME_ALT_M},0"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                            env=os.environ.copy(), cwd=ROOT)


def _start_api() -> subprocess.Popen:
    print("[fly] starting trigger API (uvicorn)")
    env = os.environ.copy()
    env.setdefault("MAVLINK_CONNECTION", f"tcp:127.0.0.1:{SITL_PORT}")
    env["HOME_LAT"] = str(HOME_LAT)
    env["HOME_LON"] = str(HOME_LON)
    env["SITL_MODE"] = "1"
    cmd = [sys.executable, "-m", "uvicorn", "trigger_api.main:app",
           "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                            env=env, cwd=ROOT)


def _trigger() -> str:
    payload = {"lat": TARGET_LAT, "lon": TARGET_LON, "priority": "high",
               "incident_type": "demo_my_coords", "altitude_m": ALT_M, "hover_s": HOVER_S}
    r = requests.post(f"{API_URL}/trigger", json=payload, timeout=10)
    r.raise_for_status()
    data = r.json()
    print(f"[fly] mission queued: {data['mission_id']} (ETA {data['estimated_arrival_s']}s, "
          f"target {data['target']})")
    return data["mission_id"]


def _telem() -> Optional[dict]:
    try:
        r = requests.get(f"{API_URL}/telemetry", timeout=5)
        if r.ok:
            return r.json()
    except Exception:
        return None
    return None


def _mission(mid: str) -> Optional[dict]:
    try:
        r = requests.get(f"{API_URL}/mission/{mid}", timeout=5)
        if r.ok:
            return r.json()
    except Exception:
        return None
    return None


def _print_progress(t: dict) -> None:
    lat, lon, alt = t.get("lat"), t.get("lon"), t.get("alt_m")
    state = t.get("state") or "?"
    alt_str = f"{alt:5.1f}" if isinstance(alt, (int, float)) else "  -  "
    bat = t.get("battery_pct")
    if lat is not None and lon is not None:
        d_home = _haversine(HOME_LAT, HOME_LON, lat, lon)
        d_target = _haversine(TARGET_LAT, TARGET_LON, lat, lon)
        print(f"[fly] state={state:<10s} alt={alt_str}m  d_target={d_target:7.1f}m  "
              f"d_home={d_home:7.1f}m  bat={bat}")
    else:
        print(f"[fly] state={state}  (no GPS fix yet)")


def run() -> Tuple[bool, str]:
    sitl_proc = api_proc = None
    failures = []
    checks = {"sitl_listening": False, "api_listening": False, "vehicle_connected": False,
              "armed": False, "took_off": False, "reached_target": False,
              "returned_home": False, "landed": False}
    try:
        if not _clear_stale_sitl():
            return False, f"port {SITL_PORT} occupied by a process we couldn't clear"
        sitl_proc = _start_sitl()
        if not _wait_for("SITL port 5760", lambda: _port_listening("127.0.0.1", SITL_PORT), 120):
            return False, "SITL never started"
        checks["sitl_listening"] = True
        print("[fly] SITL port is up")

        api_proc = _start_api()
        if not _wait_for("API port 8000", lambda: _port_listening("127.0.0.1", 8000), 60):
            return False, "API never started"
        checks["api_listening"] = True
        print("[fly] API is up")

        def _connected():
            try:
                r = requests.get(f"{API_URL}/health", timeout=3)
                return bool(r.ok and r.json().get("vehicle_connected"))
            except Exception:
                return False
        if _wait_for("vehicle to connect", _connected, 180):
            checks["vehicle_connected"] = True
        else:
            print("[fly] note: eager connect didn't finish; triggering anyway")

        t0 = _telem()
        bat0 = (t0 or {}).get("battery_pct")
        if bat0 is not None and bat0 < 90:
            return False, f"SITL battery at {bat0}% before launch — stale simulator"

        mid = _trigger()
        deadline = time.time() + MISSION_TIMEOUT_S
        last_print = 0.0
        max_alt = 0.0
        min_target = float("inf")
        rtl_seen = False

        while time.time() < deadline:
            t = _telem()
            m = _mission(mid)
            if t is None:
                time.sleep(1)
                continue
            if t.get("armed"):
                checks["armed"] = True
            if t.get("alt_m") and t["alt_m"] > max_alt:
                max_alt = t["alt_m"]
            if max_alt >= ALT_M * 0.8:
                checks["took_off"] = True
            if t.get("lat") is not None and t.get("lon") is not None:
                d = _haversine(TARGET_LAT, TARGET_LON, t["lat"], t["lon"])
                min_target = min(min_target, d)
                if d <= TOLERANCE_M:
                    checks["reached_target"] = True
            if t.get("state") == "RTL":
                rtl_seen = True
            if t.get("state") in ("LANDED", "COMPLETED"):
                checks["landed"] = True
                if t.get("lat") is not None:
                    if _haversine(HOME_LAT, HOME_LON, t["lat"], t["lon"]) <= 10.0:
                        checks["returned_home"] = True
            now = time.time()
            if now - last_print > 4.0:
                _print_progress(t)
                last_print = now
            if m and m.get("status") in ("done", "failed", "aborted"):
                print(f"[fly] mission finished: status={m['status']} final_state={m.get('final_state')}")
                break
            time.sleep(1.0)
        else:
            failures.append(f"mission timed out after {MISSION_TIMEOUT_S}s")

        print(f"[fly] closest approach to target: {min_target:.1f}m (tolerance {TOLERANCE_M}m)")
        if not rtl_seen:
            failures.append("RTL phase never observed")
    finally:
        _kill_tree(api_proc, "api")
        _kill_tree(sitl_proc, "sitl")

    print("\n[fly] check summary:")
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if failures:
        print("\n[fly] additional failures:")
        for f in failures:
            print(f"  - {f}")

    required = ["sitl_listening", "api_listening", "armed", "took_off",
                "reached_target", "returned_home", "landed"]
    ok = all(checks[k] for k in required)
    return ok, "all required checks passed" if ok else "one or more required checks failed"


def main() -> int:
    print("=" * 64)
    print("  FLY FROM MY COORDINATES — NAGPUR -> RANDOM NEARBY TARGET")
    print(f"  HOME  {HOME_LAT}, {HOME_LON}")
    print(f"  TARGET {TARGET_LAT}, {TARGET_LON}  "
          f"({_haversine(HOME_LAT, HOME_LON, TARGET_LAT, TARGET_LON):.0f} m away)")
    print("=" * 64)
    start = time.time()
    ok, msg = run()
    print("\n" + "=" * 64)
    print(f"  {'PASS' if ok else 'FAIL'}  ({time.time() - start:.1f}s) — {msg}")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
