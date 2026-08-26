from __future__ import annotations

import numpy as np
import pytest

from hub.audio_analysis import AudioAnalysisSession


def tone(freq: float, amplitude: float = 0.4, seconds: float = 0.1, sr: int = 16000):
    t = np.arange(int(seconds * sr)) / sr
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_dominant_frequency_tracks_a_tone():
    analyzer = AudioAnalysisSession(baseline_ms=0)
    frame = analyzer.process(tone(1200), 16000, 100)
    assert frame.dominant_frequency_hz == pytest.approx(1200, abs=80)
    assert frame.rms_amplitude > 0.2


def test_sustained_peak_requires_duration_and_history_is_bounded():
    analyzer = AudioAnalysisSession(baseline_ms=100, min_sustained_ms=300,
                                    rms_multiplier=1.2, energy_multiplier=1.2,
                                    history_size=3)
    analyzer.process(tone(500, 0.02), 16000, 0)
    short = analyzer.process(tone(1200, 0.5), 16000, 200)
    assert short.state == "POTENTIAL_DISTRESS"
    confirmed = analyzer.process(tone(1200, 0.5), 16000, 500)
    assert confirmed.state == "PEAK_SUSTAINED"
    analyzer.process(tone(1200, 0.5), 16000, 600)
    assert len(analyzer.history) == 3


def test_short_gap_keeps_peak_but_long_gap_resets_it():
    analyzer = AudioAnalysisSession(baseline_ms=0, min_sustained_ms=300,
                                    max_gap_ms=100, rms_multiplier=1.1, energy_multiplier=1.1)
    analyzer.process(tone(1200), 16000, 0)
    brief_gap = analyzer.process(np.zeros(1600), 16000, 80)
    assert brief_gap.peak_duration_ms > 0
    reset = analyzer.process(np.zeros(1600), 16000, 250)
    assert reset.state == "NORMAL_AUDIO"
    assert reset.peak_duration_ms == 0
