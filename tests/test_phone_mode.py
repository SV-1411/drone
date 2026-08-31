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


def _voiced_call(f0, duration, amplitude, noise=0.0):
    """A deterministic voiced-call fixture for prosody-gate regression tests."""
    sr = 16000
    x = np.zeros(sr * 2, dtype=np.float32)
    start, count = int(sr * 0.45), int(sr * duration)
    t = np.arange(count, dtype=np.float32) / sr
    x[start:start + count] = amplitude * (
        np.sin(2 * np.pi * f0 * t) + 0.35 * np.sin(2 * np.pi * 2 * f0 * t)
    )
    if noise:
        x += np.random.default_rng(42).normal(0, noise, x.size).astype(np.float32)
    return x


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


def test_trained_stage1_nn_catches_cry_when_yamnet_is_uncertain(monkeypatch):
    """The project-trained model must remain in the live path as the fallback
    for cries that generic AudioSet YAMNet does not score strongly enough."""
    from hub import webapp
    import hub.yamnet_detector as yamnet_detector

    class UncertainYamnet:
        def distress_label(self, audio):
            return 0.05, "Speech"

    class CryModel:
        def infer(self, audio):
            return 2, 0.95  # Stage1NN class 2 is cry

    monkeypatch.setattr(yamnet_detector, "get_detector", lambda: UncertainYamnet())
    monkeypatch.setattr(webapp, "_stage1", lambda: CryModel())
    triggered, label, confidence, event = webapp.stage1_phone(
        np.full(32000, 0.10, dtype=np.float32)
    )
    assert (triggered, label, confidence, event) == (True, "cry", 0.95, 3)


def test_spoken_stress_gate_accepts_quiet_short_stressed_word_with_noise():
    from hub.spoken_stress import analyse_spoken_stress
    result = analyse_spoken_stress(_voiced_call(230, 0.28, 0.006, noise=0.0005))
    assert result.accepted
    assert result.snr_db >= 6.0 and result.peak_pitch_hz >= 210


def test_spoken_stress_gate_accepts_a_brief_stressed_emergency_word():
    """Voiced duration excludes initial/final consonants of a short word."""
    from hub.spoken_stress import analyse_spoken_stress
    result = analyse_spoken_stress(_voiced_call(315, 0.23, 0.006, noise=0.0005))
    assert result.active_duration_s >= 0.15
    assert result.accepted


def test_spoken_stress_gate_rejects_normal_word_and_white_noise():
    from hub.spoken_stress import analyse_spoken_stress
    normal = analyse_spoken_stress(_voiced_call(130, 0.28, 0.08))
    street_noise = analyse_spoken_stress(
        np.random.default_rng(9).normal(0, 0.03, 32000).astype(np.float32)
    )
    assert not normal.accepted
    assert not street_noise.accepted


def test_keyword_normalization_keeps_elongated_emergency_words_but_not_hello():
    from hub.distress_keywords import match_distress_keyword
    assert match_distress_keyword("heeelp") == "help"
    assert match_distress_keyword("bachaaaooo") == "bachao"
    assert match_distress_keyword("bajao mujhe") == "bachao mujhe"
    assert match_distress_keyword("batao") == "bachao"
    assert match_distress_keyword("madat karo") == "madad karo"
    assert match_distress_keyword("halp me") == "help me"
    assert match_distress_keyword("hello there") is None


def test_speech_alert_needs_stressed_keyword_audio(base):
    normal = requests.post(
        base + "/speech-alert?transcript=bachao&confidence=0.95",
        data=_wav(_voiced_call(130, 0.28, 0.08)),
        headers={"content-type": "audio/wav"},
    ).json()
    assert normal["ok"] and not normal["distress"]

    stressed = requests.post(
        base + "/speech-alert?transcript=bachaaaooo&confidence=0.00",
        data=_wav(_voiced_call(230, 0.28, 0.006, noise=0.0005)),
        headers={"content-type": "audio/wav"},
    ).json()
    assert stressed["ok"] and stressed["distress"]
    assert stressed["stage1"] == "stressed_keyword"
    assert stressed["stress"]["accepted"]
    assert stressed["dispatched"]
    diagnostics = requests.get(base + "/speech-diagnostics").json()
    assert diagnostics[0]["keyword"] == "bachao"
    assert diagnostics[0]["accepted"]


def test_phone_audio_does_not_promote_prosody_without_an_emergency_word(base):
    """A high-pitched voice alone must not create a random emergency alert."""
    response = requests.post(
        base + "/phone-alert?lat=21.1466&lon=79.0882",
        data=_wav(_voiced_call(230, 0.28, 0.006, noise=0.0005)),
        headers={"content-type": "audio/wav"},
    ).json()
    assert response["ok"] and not response["distress"]
    assert response["stress"]["accepted"]


def test_calibrated_voice_window_dispatches_through_the_existing_pipeline(base, monkeypatch):
    """A fine-tuned Render model confirmation must reach fusion + dispatch.

    The test uses the public HTTP route rather than calling the decision engine
    directly, which catches regressions in WAV decoding, temporal adaptation,
    pipeline injection and the response contract together.
    """
    from hub import webapp
    from hub.voice_decision import VOICE_CLASSES, VoiceDecisionEngine

    class StrongScreamModel:
        available = True
        model_version = "test-voice-window-v1"

        def probabilities(self, audio, sr=16000):
            result = {name: 0.0 for name in VOICE_CLASSES}
            result["scream"] = 0.96
            return result

    monkeypatch.setattr(webapp, "voice_engine", VoiceDecisionEngine(StrongScreamModel()))
    response = requests.post(
        base + "/voice-window?session_id=endpoint-test&sequence=1&lat=21.15&lon=79.09",
        data=_wav(_voiced_call(240, .30, .02)),
        headers={"content-type": "audio/wav"},
    ).json()
    assert response["ok"] and response["distress"] and response["dispatched"]
    assert response["stage1"] == "scream"
    assert response["voice"]["decision_path"] == "single-strong-scream"
    assert response["voice"]["model_version"] == "test-voice-window-v1"


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
