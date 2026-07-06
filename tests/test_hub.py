"""Unit tests for the VanniKawachh hub — packets, registry, fusion, pipeline.

No hardware, no PANNs, no network: the verifier uses the energy-heuristic
backend and the dispatcher is mocked.
"""
from __future__ import annotations

import math
import os
import struct
import sys
import wave

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hub.config import HubConfig
from hub.fusion import fuse
from hub.node_registry import Node, NodeRegistry
from hub.packets import Alert, PacketError, seal, unseal
from hub.pipeline import AlertPipeline
from hub.verifier import EnergyHeuristicBackend, Stage2Verifier

MASTER = bytes.fromhex("000102030405060708090a0b0c0d0e0f")


def _alert(counter=1, conf=0.9, pir=True, light=20) -> Alert:
    return Alert(node_id=1, counter=counter, event=1, confidence=conf,
                 pir=pir, light=light, battery_pct=88)


# ---------------------------------------------------------------------------
# packets
# ---------------------------------------------------------------------------

def test_packet_roundtrip():
    a = _alert()
    pkt = seal(MASTER, a)
    assert len(pkt) == 25
    b = unseal(MASTER, pkt)
    assert (b.node_id, b.counter, b.event) == (1, 1, 1)
    assert abs(b.confidence - 0.9) < 0.01
    assert b.pir is True and b.light == 20 and b.battery_pct == 88


def test_packet_tamper_rejected():
    pkt = bytearray(seal(MASTER, _alert()))
    pkt[10] ^= 0xFF                               # flip a ciphertext bit
    with pytest.raises(PacketError, match="MAC"):
        unseal(MASTER, bytes(pkt))


def test_packet_wrong_key_rejected():
    pkt = seal(MASTER, _alert())
    with pytest.raises(PacketError, match="MAC"):
        unseal(b"\x99" * 16, pkt)


def test_packet_replay_rejected():
    pkt = seal(MASTER, _alert(counter=5))
    unseal(MASTER, pkt, last_counter=4)           # fresh -> ok
    with pytest.raises(PacketError, match="replayed"):
        unseal(MASTER, pkt, last_counter=5)       # same counter -> replay


def test_packet_bad_length_and_magic():
    with pytest.raises(PacketError):
        unseal(MASTER, b"short")
    pkt = bytearray(seal(MASTER, _alert()))
    pkt[0] = ord("X")
    with pytest.raises(PacketError, match="magic"):
        unseal(MASTER, bytes(pkt))


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def test_registry_roundtrip(tmp_path):
    path = str(tmp_path / "nodes.json")
    reg = NodeRegistry(path)
    reg.add(Node(node_id=7, lat=28.61, lon=77.21, name="pole-7"))
    reg.save()
    reg2 = NodeRegistry(path)
    n = reg2.get(7)
    assert n is not None and n.name == "pole-7" and n.lat == 28.61
    assert reg2.get(99) is None


def test_registry_counter_persists(tmp_path):
    path = str(tmp_path / "nodes.json")
    reg = NodeRegistry(path)
    reg.add(Node(node_id=1, lat=0, lon=0))
    reg.bump_counter(1, 41)
    assert NodeRegistry(path).get(1).last_counter == 41
    reg.bump_counter(1, 40)                       # lower value never regresses
    assert NodeRegistry(path).get(1).last_counter == 41


# ---------------------------------------------------------------------------
# fusion
# ---------------------------------------------------------------------------

def test_fusion_night_dark_pir_raises_severity():
    quiet_day = fuse(_alert(pir=False, light=250), audio_score=0.5, now_hour=12.0)
    dark_night = fuse(_alert(pir=True, light=5), audio_score=0.5, now_hour=23.0)
    assert dark_night.score > quiet_day.score


def test_fusion_priority_escalates():
    sev = fuse(_alert(pir=True, light=5), audio_score=0.9, now_hour=23.0)
    assert sev.priority == "high"
    sev2 = fuse(_alert(pir=False, light=250, conf=0.2), audio_score=0.2, now_hour=12.0)
    assert sev2.priority == "normal"


# ---------------------------------------------------------------------------
# verifier (energy heuristic)
# ---------------------------------------------------------------------------

def _write_wav(path: str, freq: float, amp: float, seconds: float = 4.0,
               sr: int = 16000) -> None:
    t = np.arange(int(sr * seconds)) / sr
    x = amp * np.sin(2 * math.pi * freq * t)
    # add a burst so it looks scream-like rather than a steady tone
    x[sr:sr + sr // 2] *= 3.0
    x = np.clip(x, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def test_energy_backend_orders_scream_above_silence(tmp_path):
    loud = str(tmp_path / "loud.wav"); quiet = str(tmp_path / "quiet.wav")
    _write_wav(loud, freq=1400.0, amp=0.5)        # loud, high-pitched, bursty
    _write_wav(quiet, freq=200.0, amp=0.01)       # near-silence hum
    v = Stage2Verifier(backend=EnergyHeuristicBackend())
    assert v.verify_wav(loud) > v.verify_wav(quiet)
    assert v.verify_wav(loud) >= 0.5


# ---------------------------------------------------------------------------
# pipeline (mock dispatcher)
# ---------------------------------------------------------------------------

class _MockDispatcher:
    def __init__(self):
        self.calls = []

    def dispatch(self, lat, lon, priority, node_name=""):
        self.calls.append((lat, lon, priority, node_name))
        return "mission-test-1"


def _pipeline(tmp_path, clip_wait=0.1):
    cfg = HubConfig(
        nodes_file=str(tmp_path / "nodes.json"),
        clips_dir=str(tmp_path / "clips"),
        clip_wait_s=clip_wait,
    )
    os.makedirs(cfg.clips_dir, exist_ok=True)
    reg = NodeRegistry(cfg.nodes_file)
    reg.add(Node(node_id=1, lat=28.6178, lon=77.2137, name="pole-1"))
    reg.save()
    disp = _MockDispatcher()
    pipe = AlertPipeline(cfg, reg,
                         verifier=Stage2Verifier(backend=EnergyHeuristicBackend()),
                         dispatcher=disp)
    return pipe, disp


def test_pipeline_dispatches_on_verified_scream(tmp_path):
    pipe, disp = _pipeline(tmp_path)
    a = _alert(counter=1, pir=True, light=5)
    _write_wav(pipe.clip_path(1, 1), freq=1400.0, amp=0.5)   # clip pre-staged
    inc = pipe.process_packet(seal(MASTER, a))
    assert inc is not None and inc.dispatched
    assert disp.calls and disp.calls[0][0] == pytest.approx(28.6178)
    assert inc.mission_id == "mission-test-1"


def test_pipeline_no_dispatch_on_quiet_clip(tmp_path):
    pipe, disp = _pipeline(tmp_path)
    a = _alert(counter=1, conf=0.3, pir=False, light=250)
    _write_wav(pipe.clip_path(1, 1), freq=200.0, amp=0.01)
    inc = pipe.process_packet(seal(MASTER, a))
    assert inc is not None and not inc.dispatched
    assert disp.calls == []


def test_pipeline_rejects_unknown_node_and_replay(tmp_path):
    pipe, disp = _pipeline(tmp_path)
    stranger = Alert(node_id=42, counter=1, event=1, confidence=0.9,
                     pir=True, light=0, battery_pct=50)
    assert pipe.process_packet(seal(MASTER, stranger)) is None

    a = _alert(counter=3)
    _write_wav(pipe.clip_path(1, 3), freq=1400.0, amp=0.5)
    assert pipe.process_packet(seal(MASTER, a)) is not None
    assert pipe.process_packet(seal(MASTER, a)) is None       # replayed
    assert len(disp.calls) == 1


def test_pipeline_degrades_without_clip(tmp_path):
    """No clip -> stage-1 confidence is taken at a 0.6 haircut. With a 0.7
    stage-1 score the degraded audio score (0.42) sits below the verify
    threshold (0.50), so no dispatch regardless of the fusion context
    (fusion uses wall-clock night boost, so keep this branch deterministic)."""
    pipe, disp = _pipeline(tmp_path, clip_wait=0.1)
    a = _alert(counter=1, conf=0.7)                            # no clip staged
    inc = pipe.process_packet(seal(MASTER, a))
    assert inc is not None
    assert inc.audio_score == pytest.approx(0.7 * 0.6, abs=0.01)
    assert not inc.dispatched                                  # degraded < verify threshold
    assert disp.calls == []
