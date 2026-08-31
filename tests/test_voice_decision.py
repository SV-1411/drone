from __future__ import annotations

import numpy as np

from hub.voice_decision import VOICE_CLASSES, VoiceDecisionEngine, log_mel


class FakeBackend:
    available = True
    model_version = "test-v1"

    def __init__(self, scores):
        self.scores = list(scores)

    def probabilities(self, audio, sr=16000):
        top = self.scores.pop(0)
        out = {name: 0.0 for name in VOICE_CLASSES}
        out.update(top)
        return out


def _quiet_unvoiced():
    # Whisper-like/no-F0 fixture: it must reach the trained model rather than
    # being rejected by the old pitch gate before inference.
    rng = np.random.default_rng(5)
    x = np.zeros(32000, dtype=np.float32)
    x[8000:13000] = rng.normal(0, .008, 5000)
    return x


def test_log_mel_has_exported_model_shape():
    assert log_mel(np.zeros(32000, dtype=np.float32)).shape == (96, 64)


def test_one_calibrated_strong_short_scream_confirms():
    engine = VoiceDecisionEngine(FakeBackend([{"scream": .93}]))
    result = engine.analyse(_quiet_unvoiced(), session_id="one")
    assert result.distress_confirmed
    assert result.event_type == "scream"
    assert result.decision_path == "single-strong-scream"


def test_two_overlapping_moderate_cry_windows_confirm():
    engine = VoiceDecisionEngine(FakeBackend([{"cry_wail": .70}, {"cry_wail": .69}]))
    first = engine.analyse(_quiet_unvoiced(), session_id="two")
    second = engine.analyse(_quiet_unvoiced(), session_id="two")
    assert not first.distress_confirmed
    assert second.distress_confirmed
    assert second.decision_path == "two-window-cry_wail"


def test_whisper_like_keyword_can_use_model_without_f0():
    engine = VoiceDecisionEngine(FakeBackend([{"distressed_speech": .60}]))
    result = engine.analyse(_quiet_unvoiced(), session_id="whisper", keyword="bachao")
    assert result.distress_confirmed
    assert result.decision_path == "keyword+model"


def test_background_does_not_confirm():
    engine = VoiceDecisionEngine(FakeBackend([{"background_interference": .99, "scream": .05}]))
    result = engine.analyse(_quiet_unvoiced(), session_id="noise")
    assert not result.distress_confirmed
