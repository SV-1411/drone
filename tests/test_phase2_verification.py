"""Phase-2 unit tests that do not require the trained model artifact."""
import numpy as np

from hub.audio_features import FEATURE_NAMES, extract_features
from hub.distress_classifier import build_feature_vector
from hub.temporal_verifier import TemporalDistressVerifier


def test_classifier_feature_vector_has_stable_order_and_finite_values():
    sr = 16000
    t = np.arange(sr, dtype=np.float32) / sr
    audio = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    yamnet = np.zeros(521, dtype=np.float32)
    yamnet[1] = 0.5
    features = build_feature_vector(audio, sr, yamnet)
    assert features.shape == (521 + len(FEATURE_NAMES),)
    assert np.isfinite(features).all()


def test_temporal_gate_rejects_single_transient():
    gate = TemporalDistressVerifier(threshold=0.70, min_positive_frames=3)
    assert gate.update(0.95, 0.80).distress_confirmed is False
    assert gate.update(0.20, 0.80).distress_confirmed is False
    assert gate.update(0.95, 0.80).distress_confirmed is False


def test_temporal_gate_confirms_persistent_distress():
    gate = TemporalDistressVerifier(threshold=0.70, min_positive_frames=3)
    gate.update(0.80, 0.40)
    gate.update(0.85, 0.50)
    result = gate.update(0.92, 0.75)
    assert result.distress_confirmed is False
    # The first two frames are rejected because the YAMNet support gate failed.
    gate.reset()
    gate.update(0.80, 0.75)
    gate.update(0.85, 0.80)
    result = gate.update(0.92, 0.90)
    assert result.distress_confirmed is True
    assert result.positive_frames == 3


def test_temporal_gate_resets_after_negative_frame():
    gate = TemporalDistressVerifier(threshold=0.70, min_positive_frames=3)
    gate.update(0.90, 0.90)
    gate.update(0.90, 0.90)
    gate.update(0.20, 0.90)
    result = gate.update(0.90, 0.90)
    assert result.distress_confirmed is False
    assert result.positive_frames == 1
