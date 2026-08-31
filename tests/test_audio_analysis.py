from __future__ import annotations

import numpy as np
import pytest

from hub.audio_analysis import AudioAnalysisSession


def tone(freq: float, amplitude: float = 0.4, seconds: float = 0.1, sr: int = 16000):
    t = np.arange(int(seconds * sr)) / sr
    return amplitude * np.sin(2 * np.pi * freq * t)


def rough_tone(freq: float, amplitude: float = 0.4, rough_freq: float = 80.0,
               seconds: float = 0.1, sr: int = 16000):
    """Tone with amplitude modulation in the roughness band (30-150 Hz)."""
    t = np.arange(int(seconds * sr)) / sr
    carrier = amplitude * np.sin(2 * np.pi * freq * t)
    modulator = 1.0 + 0.8 * np.sin(2 * np.pi * rough_freq * t)
    return carrier * modulator


def test_dominant_frequency_tracks_a_tone():
    analyzer = AudioAnalysisSession(baseline_ms=0)
    frame = analyzer.process(tone(800), 16000, 100)
    assert frame.dominant_frequency_hz == pytest.approx(800, abs=80)
    assert frame.rms_amplitude > 0.2


def test_roughness_detected_in_amplitude_modulated_tone():
    analyzer = AudioAnalysisSession(baseline_ms=0)
    frame = analyzer.process(rough_tone(800, 0.4, rough_freq=80), 16000, 100)
    assert frame.roughness > 0.0


def test_sustained_peak_requires_duration_and_history_is_bounded():
    analyzer = AudioAnalysisSession(baseline_ms=100, min_sustained_ms=300,
                                    rms_multiplier=1.2, energy_multiplier=1.2,
                                    roughness_threshold=0.0, peak_energy_threshold=0.0,
                                    history_size=3)
    analyzer.process(tone(400, 0.02), 16000, 0)
    short = analyzer.process(tone(800, 0.5), 16000, 200)
    assert short.state == "POTENTIAL_DISTRESS"
    confirmed = analyzer.process(tone(800, 0.5), 16000, 500)
    assert confirmed.state == "PEAK_SUSTAINED"
    analyzer.process(tone(800, 0.5), 16000, 600)
    assert len(analyzer.history) == 3


def test_short_gap_keeps_peak_but_long_gap_resets_it():
    analyzer = AudioAnalysisSession(baseline_ms=0, min_sustained_ms=300,
                                    max_gap_ms=100, rms_multiplier=1.1, energy_multiplier=1.1,
                                    roughness_threshold=0.0, peak_energy_threshold=0.0)
    analyzer.process(tone(800), 16000, 0)
    brief_gap = analyzer.process(np.zeros(1600), 16000, 80)
    assert brief_gap.peak_duration_ms > 0
    reset = analyzer.process(np.zeros(1600), 16000, 250)
    assert reset.state == "NORMAL_AUDIO"
    assert reset.peak_duration_ms == 0


def test_peak_requires_roughness_or_peak_energy():
    """Pure sine at 800 Hz should NOT trigger peak with default thresholds."""
    analyzer = AudioAnalysisSession(baseline_ms=0, rms_multiplier=1.0, energy_multiplier=1.0)
    frame = analyzer.process(tone(800, 0.5), 16000, 100)
    assert not frame.is_peak
    assert frame.roughness < 0.8  # pure sine has low roughness
    # Amplitude-modulated tone SHOULD trigger peak
    frame2 = analyzer.process(rough_tone(800, 0.5, rough_freq=80), 16000, 200)
    assert frame2.is_peak
    assert frame2.roughness > 0.8


def test_frame_has_roughness_and_peak_energy_band_fields():
    analyzer = AudioAnalysisSession(baseline_ms=0)
    frame = analyzer.process(tone(800, 0.3), 16000, 100)
    assert hasattr(frame, "roughness")
    assert hasattr(frame, "peak_energy_band")
    assert isinstance(frame.roughness, float)
    assert isinstance(frame.peak_energy_band, float)


def test_new_default_vocal_range():
    """Default vocal range should be 300-1500 Hz per Arnal 2015."""
    analyzer = AudioAnalysisSession()
    assert analyzer.vocal_min_hz == 300.0
    assert analyzer.vocal_max_hz == 1500.0


def test_summary_includes_roughness_baseline():
    analyzer = AudioAnalysisSession(baseline_ms=200)
    analyzer.process(tone(800, 0.3), 16000, 0)
    analyzer.process(tone(800, 0.3), 16000, 100)
    summary = analyzer.summary()
    assert "roughness" in summary["baseline"]
