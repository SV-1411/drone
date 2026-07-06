"""Phase-0 demo — the complete VanniKawachh chain with zero hardware.

    scream (synthesized WAV) ─▶ node alert (sealed packet, simulated)
      ─▶ hub: unseal → Stage-2 verify → fuse → dispatch
      ─▶ drone stack: queue → SITL flight → hover-record → kit drop → RTL

Run from project root:

    python scripts/demo_phase0.py

Spawns dronekit-sitl + the trigger API exactly like the e2e test, then runs
the hub pipeline in-process with a simulated node. Prints the chain as it
happens; exits 0 on a completed mission.
"""
from __future__ import annotations

import math
import os
import socket
import subprocess
import sys
import time
import wave

import numpy as np
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Windows consoles default to cp1252 — force UTF-8 so arrows etc. print fine.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from hub.config import HubConfig
from hub.node_registry import Node, NodeRegistry
from hub.packets import Alert, seal
from hub.pipeline import AlertPipeline
from hub.verifier import EnergyHeuristicBackend, Stage2Verifier

HOME_LAT, HOME_LON = 28.6139, 77.2090
NODE_LAT, NODE_LON = 28.6178, 77.2137          # "pole" ~600 m NE of home
API = "http://127.0.0.1:8000"
SITL_PORT = 5760


def say(msg: str) -> None:
    print(f"\n>>> {msg}", flush=True)


def port_up(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def wait_for(name, fn, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(1.0)
    print(f"[demo] timeout waiting for {name}")
    return False


def kill_tree(p):
    if p is None or p.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        p.terminate()


def synth_scream_wav(path: str, sr: int = 16000, seconds: float = 4.0) -> None:
    """A loud, high-pitched, bursty clip that reads as distress to the
    dev verifier (Phase 1 replaces this with real recorded test audio)."""
    t = np.arange(int(sr * seconds)) / sr
    f = 900 + 500 * np.sin(2 * math.pi * 2.6 * t)          # wailing pitch sweep
    x = 0.55 * np.sin(2 * math.pi * f * t)
    x[int(0.8 * sr):int(1.6 * sr)] *= 2.2                   # scream burst
    x += 0.02 * np.random.default_rng(3).normal(size=x.shape)
    x = np.clip(x, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def main() -> int:
    print("=" * 64)
    print("  VANNIKAWACHH — PHASE 0 FULL-CHAIN DEMO (SITL, no hardware)")
    print("=" * 64)
    sitl = api = None
    try:
        # -- 1. flight stack up (same recipe as tests/test_full_mission.py) --
        say("starting SITL + trigger API (the response layer)")
        env = os.environ.copy()
        sitl = subprocess.Popen(
            [sys.executable, "-m", "dronekit_sitl", "copter-3.3",
             f"--home={HOME_LAT},{HOME_LON},584,0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, cwd=ROOT, env=env)
        if not wait_for("SITL", lambda: port_up(SITL_PORT), 120):
            return 1
        env["SITL_MODE"] = "1"
        env.setdefault("MAVLINK_CONNECTION", f"tcp:127.0.0.1:{SITL_PORT}")
        api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "trigger_api.main:app",
             "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, cwd=ROOT, env=env)
        if not wait_for("API", lambda: port_up(8000), 60):
            return 1
        wait_for("vehicle connect", lambda: (
            requests.get(f"{API}/health", timeout=3).json().get("vehicle_connected")
        ), 180)

        # -- 2. hub up (in-process), with the demo node registered ----------
        say("hub online — node 1 'demo-pole-1' registered at the incident site")
        demo_dir = os.path.join(ROOT, "logs", "demo_phase0")
        os.makedirs(os.path.join(demo_dir, "clips"), exist_ok=True)
        cfg = HubConfig(nodes_file=os.path.join(demo_dir, "nodes.json"),
                        clips_dir=os.path.join(demo_dir, "clips"),
                        clip_wait_s=2.0)
        reg = NodeRegistry(cfg.nodes_file)
        reg.add(Node(node_id=1, lat=NODE_LAT, lon=NODE_LON, name="demo-pole-1"))
        reg.save()
        pipeline = AlertPipeline(
            cfg, reg, verifier=Stage2Verifier(backend=EnergyHeuristicBackend()))
        print(f"[demo] stage-2 backend: {type(pipeline.verifier.backend).name}")

        # -- 3. the incident --------------------------------------------------
        say('a scream ("Bachao!") reaches node 1 — Stage-1 CNN fires on-device')
        alert = Alert(node_id=1, counter=1, event=1, confidence=0.86,
                      pir=True, light=15, battery_pct=93)
        packet = seal(bytes.fromhex(cfg.master_key_hex), alert)
        print(f"[demo] sealed LoRa packet ({len(packet)} bytes): {packet.hex()}")
        synth_scream_wav(pipeline.clip_path(1, 1))
        print("[demo] 4 s evidence clip uploaded over WiFi (simulated)")

        # -- 4. hub decision ---------------------------------------------------
        say("hub: unseal → verify → fuse → dispatch")
        inc = pipeline.process_packet(packet)
        if inc is None or not inc.dispatched:
            print("[demo] FAIL — hub did not dispatch"); return 1
        print(f"[demo] severity={inc.severity:.2f} [{inc.priority}] "
              f"mission={inc.mission_id}")

        # -- 5. watch the flight ----------------------------------------------
        say("drone dispatched — watching the mission (this takes ~5 min)")
        deadline = time.time() + 420
        last = ""
        while time.time() < deadline:
            m = requests.get(f"{API}/mission/{inc.mission_id}", timeout=5).json()
            t = requests.get(f"{API}/telemetry", timeout=5).json()
            line = f"state={t.get('state'):<10} alt={t.get('alt_m') or 0:5.1f}m"
            if line != last:
                print(f"[demo] {line}")
                last = line
            if m.get("status") in ("done", "failed", "aborted"):
                say(f"mission finished: {m['status']} ({m.get('final_state')})")
                ok = m.get("status") == "done"
                print("\n" + "=" * 64)
                print(f"  {'DEMO PASS' if ok else 'DEMO FAIL'} — scream → node → hub "
                      f"→ drone → kit drop → home")
                print("=" * 64)
                return 0 if ok else 1
            time.sleep(2.0)
        print("[demo] FAIL — mission timed out")
        return 1
    finally:
        kill_tree(api)
        kill_tree(sitl)


if __name__ == "__main__":
    raise SystemExit(main())
