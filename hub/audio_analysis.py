"""Explainable, bounded audio-feature analysis for VanniKawachh.

This module deliberately provides evidence rather than a second dispatch
decision.  YAMNet/Stage-2 and fusion remain the central arbiters; callers use
the peak state to explain how a clip behaved over time.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import math
import os
from typing import Iterable

import numpy as np


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class AudioAnalysisFrame:
    timestamp_ms: int
    rms_amplitude: float
    peak_amplitude: float
    dominant_frequency_hz: float
    peak_magnitude: float
    spectral_energy: float
    noise_floor: float
    frequency_threshold_hz: float
    is_peak: bool
    peak_duration_ms: int
    state: str
    roughness: float = 0.0
    peak_energy_band: float = 0.0

    def public(self) -> dict:
        return asdict(self)


class AudioAnalysisSession:
    """FFT features plus hysteretic, duration-based peak evidence.

    Baseline frames establish relative RMS and energy thresholds.  The vocal
    range is intentionally broad and is only one condition in ``is_peak``.
    """

    def __init__(self, *, baseline_ms: int | None = None,
                 min_sustained_ms: int | None = None,
                 max_gap_ms: int | None = None,
                 rms_multiplier: float | None = None,
                 energy_multiplier: float | None = None,
                 vocal_min_hz: float | None = None,
                 vocal_max_hz: float | None = None,
                 roughness_threshold: float | None = None,
                 peak_energy_min_hz: float | None = None,
                 peak_energy_max_hz: float | None = None,
                 peak_energy_threshold: float | None = None,
                 history_size: int = 180):
        self.baseline_ms = baseline_ms if baseline_ms is not None else int(_env_float("AUDIO_BASELINE_MS", 2000))
        self.min_sustained_ms = min_sustained_ms if min_sustained_ms is not None else int(_env_float("AUDIO_MIN_SUSTAINED_MS", 2000))
        self.max_gap_ms = max_gap_ms if max_gap_ms is not None else int(_env_float("AUDIO_MAX_PEAK_GAP_MS", 180))
        self.rms_multiplier = rms_multiplier if rms_multiplier is not None else _env_float("AUDIO_RMS_MULTIPLIER", 2.2)
        self.energy_multiplier = energy_multiplier if energy_multiplier is not None else _env_float("AUDIO_ENERGY_MULTIPLIER", 2.0)
        # F0 distress band: 300-1500 Hz (Arnal 2015, Engelberg 2021)
        self.vocal_min_hz = vocal_min_hz if vocal_min_hz is not None else _env_float("AUDIO_VOCAL_MIN_HZ", 300.0)
        self.vocal_max_hz = vocal_max_hz if vocal_max_hz is not None else _env_float("AUDIO_VOCAL_MAX_HZ", 1500.0)
        # Roughness threshold: normalized power variance.
        # Screams produce ≈1.5+; pure tones ≈0.5. Default 0.8 separates them.
        self.roughness_threshold = roughness_threshold if roughness_threshold is not None else _env_float("AUDIO_ROUGHNESS_THRESHOLD", 0.8)
        # Peak energy band: 2000-3000 Hz (scream energy concentration)
        self.peak_energy_min_hz = peak_energy_min_hz if peak_energy_min_hz is not None else _env_float("AUDIO_PEAK_ENERGY_MIN_HZ", 2000.0)
        self.peak_energy_max_hz = peak_energy_max_hz if peak_energy_max_hz is not None else _env_float("AUDIO_PEAK_ENERGY_MAX_HZ", 3000.0)
        self.peak_energy_threshold = peak_energy_threshold if peak_energy_threshold is not None else _env_float("AUDIO_PEAK_ENERGY_THRESHOLD", 0.002)
        self.history: deque[AudioAnalysisFrame] = deque(maxlen=history_size)
        self._baseline: list[tuple[float, float, float, float]] = []
        self._started_ms: int | None = None
        self._peak_started_ms: int | None = None
        self._last_peak_ms: int | None = None

    def _features(self, samples: np.ndarray, sample_rate: int) -> tuple[float, float, float, float, float, float, float]:
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if x.size == 0:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        rms = float(np.sqrt(np.mean(x * x)))
        peak = float(np.max(np.abs(x)))
        window = np.hanning(x.size).astype(np.float32)
        spectrum = np.abs(np.fft.rfft(x * window))
        if spectrum.size <= 1:
            return rms, peak, 0.0, 0.0, 0.0, 0.0, 0.0
        freqs = np.fft.rfftfreq(x.size, 1.0 / sample_rate)
        meaningful = (freqs >= 80.0) & (freqs <= min(6000.0, sample_rate / 2))
        if not np.any(meaningful):
            return rms, peak, 0.0, 0.0, 0.0, 0.0, 0.0
        idx = np.flatnonzero(meaningful)[int(np.argmax(spectrum[meaningful]))]
        dominant = float(freqs[idx])
        magnitude = float(spectrum[idx] / (np.sum(spectrum[meaningful]) + 1e-9))
        total_energy = float(np.sum(np.square(spectrum[meaningful])) + 1e-9)
        energy = float(np.mean(np.square(spectrum[meaningful])))
        # Roughness: normalized variance of instantaneous power.
        # Screams (30-150 Hz AM) produce power_var >> 0.5; pure tones ≈ 0.5.
        power = x ** 2
        mean_power = float(np.mean(power))
        roughness = float(np.var(power) / (mean_power ** 2 + 1e-9)) if mean_power > 1e-8 else 0.0
        # Peak energy band: proportion of energy in 2000-3000 Hz.
        pe_mask = (freqs >= self.peak_energy_min_hz) & (freqs <= self.peak_energy_max_hz)
        peak_energy_band = float(np.sum(np.square(spectrum[pe_mask])) / total_energy) if np.any(pe_mask) else 0.0
        return rms, peak, dominant, magnitude, energy, roughness, peak_energy_band

    def process(self, samples: np.ndarray, sample_rate: int, timestamp_ms: int) -> AudioAnalysisFrame:
        rms, amplitude, freq, magnitude, energy, roughness, peak_energy_band = self._features(samples, sample_rate)
        if self._started_ms is None:
            self._started_ms = timestamp_ms
        elapsed = timestamp_ms - self._started_ms
        if elapsed < self.baseline_ms:
            self._baseline.append((rms, energy, freq, roughness))
        baseline = self._baseline or [(0.01, 1e-7, 0.0, 0.0)]
        baseline_rms = max(0.004, float(np.mean([v[0] for v in baseline])))
        baseline_energy = max(1e-7, float(np.mean([v[1] for v in baseline])))
        baseline_roughness = float(np.mean([v[3] for v in baseline]))
        positive_baseline_frequencies = [v[2] for v in baseline if v[2] > 0]
        baseline_freq = (float(np.mean(positive_baseline_frequencies))
                         if positive_baseline_frequencies else 0.0)
        frequency_threshold = max(self.vocal_min_hz, baseline_freq + 2 * float(np.std([v[2] for v in baseline])))
        # Peak requires: F0 in distress band + energy above baseline + roughness present
        # Roughness (30-150 Hz AM) is the defining scream feature per Arnal 2015
        above = (
            elapsed >= self.baseline_ms
            and rms >= baseline_rms * self.rms_multiplier
            and energy >= baseline_energy * self.energy_multiplier
            and self.vocal_min_hz <= freq <= self.vocal_max_hz
            and (roughness >= self.roughness_threshold or peak_energy_band >= self.peak_energy_threshold)
        )
        if above:
            if self._peak_started_ms is None:
                self._peak_started_ms = timestamp_ms
            self._last_peak_ms = timestamp_ms
        elif self._peak_started_ms is not None and self._last_peak_ms is not None \
                and timestamp_ms - self._last_peak_ms > self.max_gap_ms:
            self._peak_started_ms = None
            self._last_peak_ms = None
        duration = 0 if self._peak_started_ms is None else max(0, timestamp_ms - self._peak_started_ms)
        if elapsed < self.baseline_ms:
            state = "BASELINE_CALIBRATION"
        elif duration >= self.min_sustained_ms:
            state = "PEAK_SUSTAINED"
        elif self._peak_started_ms is not None:
            state = "POTENTIAL_DISTRESS"
        else:
            state = "NORMAL_AUDIO"
        frame = AudioAnalysisFrame(
            timestamp_ms=timestamp_ms, rms_amplitude=round(rms, 5), peak_amplitude=round(amplitude, 5),
            dominant_frequency_hz=round(freq, 1), peak_magnitude=round(magnitude, 5),
            spectral_energy=round(energy, 5), noise_floor=round(baseline_rms, 5),
            frequency_threshold_hz=round(frequency_threshold, 1), is_peak=above,
            peak_duration_ms=duration, state=state,
            roughness=round(roughness, 5), peak_energy_band=round(peak_energy_band, 5),
        )
        self.history.append(frame)
        return frame

    def process_clip(self, samples: np.ndarray, sample_rate: int, frame_ms: int = 100) -> AudioAnalysisFrame:
        step = max(1, int(sample_rate * frame_ms / 1000))
        final = AudioAnalysisFrame(0, 0, 0, 0, 0, 0, 0, self.vocal_min_hz, False, 0, "NORMAL_AUDIO", 0.0, 0.0)
        for index in range(0, len(samples), step):
            final = self.process(samples[index:index + step], sample_rate, index * 1000 // sample_rate)
        return final

    def summary(self) -> dict:
        latest = self.history[-1] if self.history else None
        return {
            "latest": latest.public() if latest else None,
            "history": [frame.public() for frame in self.history],
        "baseline": {
            "rms": round(float(np.mean([v[0] for v in self._baseline])) if self._baseline else 0.0, 5),
            "energy": round(float(np.mean([v[1] for v in self._baseline])) if self._baseline else 0.0, 5),
            "dominant_frequency_hz": round(float(np.mean([v[2] for v in self._baseline])) if self._baseline else 0.0, 1),
            "roughness": round(float(np.mean([v[3] for v in self._baseline])) if self._baseline else 0.0, 5),
        },
            "required_duration_ms": self.min_sustained_ms,
            "max_gap_ms": self.max_gap_ms,
        }
