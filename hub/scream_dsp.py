"""Real-audio scream detector (signal-based, no training data needed).

The Stage-1 neural net is trained on synthetic/TTS audio, so it does not
reliably fire on a REAL scream captured by a phone mic. This module scores a
clip on the actual acoustics of a scream, which are distinct from normal speech,
claps, and noise:

  * loud            -- a scream is loud and stays loud
  * high-pitched    -- fundamental well above speech (roughly 300-2500 Hz;
                       normal speech sits at ~85-255 Hz)
  * high-frequency  -- energy pushed up the spectrum (high spectral centroid)
  * voiced/tonal    -- has a real pitch (harmonic), unlike white noise / hiss
  * sustained       -- held for a fraction of a second, unlike a clap or slam

`scream_score` returns 0..1. It is used alongside the model in the phone path so
a genuine scream triggers even though the bootstrap model would miss it, while
loud non-distress sounds do not.
"""
from __future__ import annotations

import numpy as np

SR = 16000
_FRAME = 400          # 25 ms at 16 kHz
_HOP = 160            # 10 ms
_WIN = np.hanning(_FRAME).astype(np.float32)
_FREQS = np.fft.rfftfreq(_FRAME, 1.0 / SR)


def _pitch_hz(frame: np.ndarray, fmin=250.0, fmax=2600.0) -> float:
    """Autocorrelation pitch. Returns 0 if the frame is not clearly voiced."""
    w = frame - frame.mean()
    ac = np.correlate(w, w, mode="full")[len(w) - 1:]
    if ac[0] <= 1e-9:
        return 0.0
    ac = ac / ac[0]
    lo, hi = int(SR / fmax), int(SR / fmin)
    seg = ac[lo:hi]
    if seg.size == 0:
        return 0.0
    k = int(np.argmax(seg)) + lo
    if ac[k] < 0.30:                  # weak periodicity -> unvoiced (noise/hiss)
        return 0.0
    return SR / k


def _flatness(spec: np.ndarray) -> float:
    """Spectral flatness 0..1 (near 1 = noise-like, near 0 = tonal)."""
    s = spec + 1e-9
    return float(np.exp(np.mean(np.log(s))) / np.mean(s))


def scream_score(x: np.ndarray, sr: int = SR) -> float:
    x = np.asarray(x, dtype=np.float32)
    if sr != SR and x.size > 1:       # cheap resample to 16 kHz
        idx = np.linspace(0, x.size - 1, int(x.size * SR / sr)).astype(np.int64)
        x = x[idx]
    if x.size < int(0.3 * SR):
        return 0.0
    rms_global = float(np.sqrt(np.mean(x ** 2)))
    if rms_global < 0.02:             # essentially quiet -> not a scream
        return 0.0

    energies, is_scream = [], []
    for i in range(0, x.size - _FRAME, _HOP):
        w = x[i:i + _FRAME] * _WIN
        e = float(np.sqrt(np.mean(w ** 2)))
        energies.append(e)
        spec = np.abs(np.fft.rfft(w))
        tot = float(spec.sum()) + 1e-9
        centroid = float((spec * _FREQS).sum() / tot)
        hf_ratio = float(spec[_FREQS > 1500].sum() / tot)
        flat = _flatness(spec)
        pitch = _pitch_hz(w)
        frame_is_scream = (
            centroid > 1100.0 and          # energy high in the spectrum
            hf_ratio > 0.30 and            # lots of high-frequency content
            flat < 0.55 and                # tonal, not white noise
            300.0 < pitch < 2500.0         # voiced and high-pitched
        )
        is_scream.append(1 if frame_is_scream else 0)

    energies = np.asarray(energies)
    is_scream = np.asarray(is_scream)
    loud = energies > max(0.03, 0.40 * float(energies.max()))
    hits = is_scream & loud
    if loud.sum() == 0:
        return 0.0

    # longest sustained run of scream frames (each frame = 10 ms)
    longest = best = 0
    for h in hits:
        best = best + 1 if h else 0
        longest = max(longest, best)
    sustained_s = longest * _HOP / SR

    frac = float(hits.sum()) / float(loud.sum())
    sustain_factor = 1.0 if sustained_s >= 0.35 else (0.4 if sustained_s >= 0.15 else 0.1)
    loud_factor = 0.6 + 0.4 * min(1.0, rms_global / 0.10)
    return float(min(1.0, frac * sustain_factor * loud_factor))
