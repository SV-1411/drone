"""Prosodic gate for short spoken distress words.

This is deliberately used *after* a speech recognizer has identified a narrow
emergency vocabulary.  It is not a general emotion detector.  The gate asks
whether that recognised word was acoustically stressed: sustained voicing plus
either elevated F0 or speech-band spectral energy.  Keeping the linguistic and
prosodic evidence separate prevents ordinary speech from becoming an alert.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


SR = 16_000
FRAME = 400                         # 25 ms
HOP = 160                           # 10 ms
WINDOW = np.hanning(FRAME).astype(np.float32)
FREQS = np.fft.rfftfreq(FRAME, 1 / SR)


@dataclass(frozen=True)
class SpokenStressResult:
    accepted: bool
    score: float
    active_duration_s: float
    peak_pitch_hz: float
    dominant_frequency_hz: float
    rms: float
    snr_db: float
    reasons: tuple[str, ...]

    def public(self) -> dict:
        return asdict(self)


def _pitch_hz(frame: np.ndarray) -> float:
    """Autocorrelation F0 estimate for voiced speech, 80--600 Hz."""
    frame = frame - np.mean(frame)
    ac = np.correlate(frame, frame, mode="full")[len(frame) - 1:]
    if ac[0] <= 1e-10:
        return 0.0
    ac = ac / ac[0]
    lo, hi = int(SR / 600), int(SR / 80)
    segment = ac[lo:hi]
    if segment.size == 0:
        return 0.0
    lag = int(np.argmax(segment)) + lo
    return SR / lag if ac[lag] >= 0.30 else 0.0


def _longest_run(values: np.ndarray) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def analyse_spoken_stress(audio: np.ndarray, sr: int = SR) -> SpokenStressResult:
    """Score the prosody of a recognised short emergency utterance.

    A fixed loudness threshold is intentionally avoided: phone gain and the
    user's distance from the microphone make absolute amplitude unreliable.
    A tiny VAD floor only distinguishes meaningful captured audio from digital
    silence.  Duration, F0 and speech-band energy are measured on voiced
    frames, which is why a quiet but stressed ``bachaaao`` can pass while a
    normal short ``bachao`` does not.
    """
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if sr != SR and x.size > 1:
        indices = np.linspace(0, x.size - 1, round(x.size * SR / sr)).astype(np.int64)
        x = x[indices]
    if x.size < FRAME:
        return SpokenStressResult(False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ("clip too short",))

    rms = float(np.sqrt(np.mean(x * x)))
    frame_rms, pitches, centroids = [], [], []
    for offset in range(0, x.size - FRAME + 1, HOP):
        frame = x[offset:offset + FRAME] * WINDOW
        energy = float(np.sqrt(np.mean(frame * frame)))
        frame_rms.append(energy)
        spec = np.abs(np.fft.rfft(frame))
        total = float(spec.sum()) + 1e-9
        centroids.append(float(np.dot(spec, FREQS) / total))
        pitches.append(_pitch_hz(frame) if energy > 0.0015 else 0.0)

    energies = np.asarray(frame_rms)
    pitches = np.asarray(pitches)
    centroids = np.asarray(centroids)
    if not energies.size or float(energies.max()) < 0.0015:
        return SpokenStressResult(False, 0.0, 0.0, 0.0, 0.0, rms, 0.0, ("no usable microphone speech",))

    # The quietest frames estimate the surrounding street/white-noise floor.
    # All energy decisions below are relative to it, so browser gain changes do
    # not turn quiet background audio into a stressed word.
    noise_rms = float(np.percentile(energies, 20))
    snr_db = 20.0 * np.log10((float(energies.max()) + 1e-8) / (noise_rms + 1e-8))
    voice_floor = max(0.0015, noise_rms * 1.9, 0.28 * float(energies.max()))
    voiced = (energies >= voice_floor) & (pitches > 0)
    active_duration = _longest_run(voiced) * HOP / SR
    if not np.any(voiced):
        return SpokenStressResult(False, 0.0, active_duration, 0.0, 0.0, rms, round(snr_db, 2), ("no sustained voiced speech",))

    peak_pitch = float(np.percentile(pitches[voiced], 90))
    dominant_frequency = float(np.median(centroids[voiced]))
    # Prosodic evidence follows the stress literature: sustained syllable
    # duration is strongest for this elongated-call case; higher F0 and more
    # speech-band energy provide independent support. Values are bounded so the
    # score is amplitude-invariant after voice activity is established.
    duration_score = float(np.clip((active_duration - 0.30) / 0.45, 0.0, 1.0))
    pitch_score = float(np.clip((peak_pitch - 165.0) / 175.0, 0.0, 1.0))
    spectral_score = float(np.clip((dominant_frequency - 750.0) / 1050.0, 0.0, 1.0))
    score = 0.55 * duration_score + 0.35 * pitch_score + 0.10 * spectral_score
    accepted = bool(active_duration >= 0.45 and score >= 0.58 and snr_db >= 6.0)
    reasons = (
        f"voiced duration {active_duration:.2f}s (need 0.45s)",
        f"90th-percentile F0 {peak_pitch:.0f} Hz",
        f"speech-band centroid {dominant_frequency:.0f} Hz",
        f"signal-to-noise ratio {snr_db:.1f} dB (need 6.0 dB)",
    )
    return SpokenStressResult(accepted, round(float(score), 3), round(active_duration, 3),
                              round(peak_pitch, 1), round(dominant_frequency, 1),
                              round(rms, 5), round(float(snr_db), 2), reasons)
