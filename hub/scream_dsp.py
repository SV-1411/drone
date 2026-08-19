"""Real-audio vocal-distress detector (signal-based, no training data needed).

The Stage-1 neural net is trained on synthetic/TTS audio, so it does not
reliably fire on real microphone audio. This module scores a clip on the
acoustics of a distress vocalisation -- it catches BOTH a high-pitched scream
AND a loud shouted word ("bachao!", "help!"), while rejecting normal-volume
speech, claps, and noise. A distress vocalisation is:

  * loud            -- much louder than ordinary talking
  * voiced          -- a real vocal pitch (rejects hiss / white noise)
  * elevated        -- raised pitch and/or lots of high-frequency energy
                       (shouting/screaming pushes energy up the spectrum)
  * held            -- a vowel sustained briefly (rejects a clap / door slam)

`vocal_distress_score` (aliased `scream_score`) returns 0..1. Every threshold is
env-tunable so it can be loosened for a noisy demo room without code changes.
"""
from __future__ import annotations

import os

import numpy as np

SR = 16000
_FRAME = 400          # 25 ms at 16 kHz
_HOP = 160            # 10 ms
_WIN = np.hanning(_FRAME).astype(np.float32)
_FREQS = np.fft.rfftfreq(_FRAME, 1.0 / SR)


def _f(key, default):
    try:
        return float(os.environ.get(key, default))
    except ValueError:
        return default


# --- tunables (env overrides) ---
# STRICT scream-only defaults: this path is now only for WORDLESS screams; the
# spoken words (help / bachao / madad) are handled by browser speech recognition
# on the /node page, so this can afford to reject all speech, shouts, and moans.
RMS_FLOOR = _f("VD_RMS_FLOOR", 0.05)      # whole clip must be genuinely loud
PITCH_MIN = _f("VD_PITCH_MIN", 320.0)     # a scream is high-pitched (speech < 300)
PITCH_MAX = _f("VD_PITCH_MAX", 2600.0)
CENT_MIN = _f("VD_CENT_MIN", 1100.0)      # energy pushed high in the spectrum
HF_MIN = _f("VD_HF_MIN", 0.30)            # lots of high-frequency energy (>1.2 kHz)
FLAT_MAX = _f("VD_FLAT_MAX", 0.55)        # tonal, not noise
SUSTAIN_S = _f("VD_SUSTAIN_S", 0.30)      # held for a third of a second
REL_E = _f("VD_REL_E", 0.40)
ABS_E = _f("VD_ABS_E", 0.03)


def _pitch_hz(frame, fmin=PITCH_MIN, fmax=PITCH_MAX):
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
    if ac[k] < 0.28:                       # weak periodicity -> unvoiced
        return 0.0
    return SR / k


def _flatness(spec):
    s = spec + 1e-9
    return float(np.exp(np.mean(np.log(s))) / np.mean(s))


def vocal_distress_score(x, sr=SR):
    x = np.asarray(x, dtype=np.float32)
    if sr != SR and x.size > 1:
        idx = np.linspace(0, x.size - 1, int(x.size * SR / sr)).astype(np.int64)
        x = x[idx]
    if x.size < int(0.25 * SR):
        return 0.0
    rms_global = float(np.sqrt(np.mean(x ** 2)))
    if rms_global < RMS_FLOOR:             # ordinary quiet sound -> not distress
        return 0.0

    energies, hits = [], []
    hf_edge = _FREQS > 1200
    for i in range(0, x.size - _FRAME, _HOP):
        w = x[i:i + _FRAME] * _WIN
        energies.append(float(np.sqrt(np.mean(w ** 2))))
        spec = np.abs(np.fft.rfft(w))
        tot = float(spec.sum()) + 1e-9
        centroid = float((spec * _FREQS).sum() / tot)
        hf = float(spec[hf_edge].sum() / tot)
        flat = _flatness(spec)
        pitch = _pitch_hz(w)
        frame_hit = (
            PITCH_MIN < pitch < PITCH_MAX and          # voiced + elevated pitch
            (centroid > CENT_MIN or hf > HF_MIN) and    # energy pushed high
            flat < FLAT_MAX                             # tonal, not noise
        )
        hits.append(1 if frame_hit else 0)

    energies = np.asarray(energies)
    hits = np.asarray(hits)
    loud = energies > max(ABS_E, REL_E * float(energies.max()))
    fired = hits & loud
    if loud.sum() == 0:
        return 0.0

    longest = best = 0
    for h in fired:
        best = best + 1 if h else 0
        longest = max(longest, best)
    sustained_s = longest * _HOP / SR

    frac = float(fired.sum()) / float(loud.sum())
    sustain_factor = 1.0 if sustained_s >= SUSTAIN_S else 0.45
    loud_factor = 0.6 + 0.4 * min(1.0, rms_global / 0.10)
    return float(min(1.0, frac * sustain_factor * loud_factor))


# backwards-compatible name used by the webapp
scream_score = vocal_distress_score
