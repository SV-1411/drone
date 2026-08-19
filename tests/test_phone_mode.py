"""Integration test for phone test mode: upload a clip -> pipeline -> sim drone.

Runs a real uvicorn server in a thread and drives it with requests (no httpx /
TestClient dependency), which mirrors exactly what the phone does.
"""
from __future__ import annotations

import io
import os
import socket
import sys
import threading
import time
import wave

import numpy as np
import pytest
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hub.config import HubConfig
from hub.node_registry import NodeRegistry
from hub.pipeline import AlertPipeline
from hub.verifier import EnergyHeuristicBackend, Stage2Verifier


def _wav(x, sr=16000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return b.getvalue()


def _scream():
    """The committed REAL scream clip (hub/models/demo_scream.wav) -- the same
    audio the /node demo button sends. A synthetic FM sine is correctly
    rejected by the YAMNet detector (it reads as a siren), so real audio is
    the only honest test signal for the distress path."""
    with open(os.path.join(ROOT, "hub", "models", "demo_scream.wav"), "rb") as f:
        return f.read()


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    import uvicorn
    from hub import webapp
    tmp = tmp_path_factory.mktemp("hub")
    cfg = HubConfig(nodes_file=str(tmp / "n.json"), clips_dir=str(tmp / "c"))
    os.makedirs(cfg.clips_dir, exist_ok=True)
    webapp.CONFIG = cfg
    reg = NodeRegistry(cfg.nodes_file)
    pipe = AlertPipeline(cfg, reg, verifier=Stage2Verifier(backend=EnergyHeuristicBackend()))
    webapp.app.state.pipeline = pipe
    for _d in webapp.fleet.drones: _d._reset()
    port = _free_port()
    threading.Thread(target=lambda: uvicorn.run(webapp.app, host="127.0.0.1",
                     port=port, log_level="error"), daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            requests.get(url + "/drone_state", timeout=1); break
        except Exception:
            time.sleep(0.2)
    return url


def test_silence_no_dispatch(base):
    r = requests.post(base + "/phone-alert?lat=1&lon=1",
                      data=_wav(np.zeros(32000)), headers={"content-type": "audio/wav"})
    j = r.json()
    assert j["ok"] and not j["distress"]


def test_scream_dispatches_sim_drone(base):
    requests.get(base + "/drone_state")               # ensure up
    from hub import webapp
    for _d in webapp.fleet.drones: _d._reset()
    r = requests.post(base + "/phone-alert?lat=21.15&lon=79.09",
                      data=_scream(), headers={"content-type": "audio/wav"})
    j = r.json()
    assert j["ok"] and j["distress"] and j["dispatched"]
    assert j["mission_id"].startswith("sim")
    d = requests.get(base + "/drone_state").json()
    assert d["state"] != "IDLE" and d["target"] == [21.15, 79.09]


def test_new_alert_moves_drone_to_new_location():
    """A distress from a different location must cancel the current mission and
    fly to the new spot (was a bug: the drone stayed put while busy)."""
    from hub.sim_drone import SimDrone
    d = SimDrone()
    d.dispatch(28.6139, 77.2090, node_name="A"); time.sleep(0.3)
    m2 = d.dispatch(21.1466, 79.0889, node_name="B"); time.sleep(0.3)
    s = d.snapshot()
    assert s["target"] == [21.1466, 79.0889] and s["mission_id"] == m2


def test_pages_render(base):
    node = requests.get(base + "/node").text
    assert "SIMULATE DISTRESS" in node and "Use my current location" in node
    dash = requests.get(base + "/").text
    assert "VanniKawachh" in dash and "Acoustic distress network" in dash
    assert "DRONE UNIT" in requests.get(base + "/drone-phone").text


def test_drone_phone_reports_and_shows_on_dashboard(base):
    from hub import webapp
    for _d in webapp.fleet.drones: _d._reset()
    webapp.phone_drone.reset()
    # a scream dispatches and assigns the incident to a drone phone
    requests.post(base + "/phone-alert?lat=21.20&lon=79.10", data=_scream(),
                  headers={"content-type": "audio/wav"})
    m = requests.get(base + "/drone-mission").json()
    assert m["has_mission"] and m["target"] == [21.20, 79.10]
    # the drone phone reports its GPS as it moves
    requests.post(base + "/drone-report?lat=21.203&lon=79.10&state=ENROUTE&kit=0")
    d = requests.get(base + "/drone_state").json()
    assert d["source"] == "phone" and d["state"] == "ENROUTE"
    assert abs(d["lat"] - 21.203) < 1e-6
