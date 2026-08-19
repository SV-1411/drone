"""Stage-2 audio verification.

Three backends, auto-selected in order:

* **PANNs** (production, on the Pi 5): pretrained AudioSet tagging model
  (`pip install panns-inference torch`). Distress score = summed probability
  over the distress-relevant AudioSet classes (screaming, shouting, crying,
  yelling, wail, ...). Use CNN14 (default) or a lighter checkpoint if the Pi
  is slow.
* **YAMNet** (light real model, `hub/yamnet_detector.py`): the same AudioSet
  distress classes from a 16 MB TFLite model — a real detector wherever a
  TFLite runtime exists but torch/PANNs doesn't.
* **Energy heuristic** (dev/SITL fallback, no ML runtime needed): loud,
  high-band, bursty audio scores high. This exists so the whole chain runs on
  any machine — it is NOT a claim of detection accuracy and must be labelled
  as the fallback in any results.
"""
from __future__ import annotations

import logging
import wave
from typing import Optional

import numpy as np

log = logging.getLogger("hub.verifier")

# AudioSet label fragments that count toward the distress score
DISTRESS_LABELS = ("scream", "shout", "yell", "crying", "wail", "groan",
                   "whimper", "screaming")


def load_wav_mono(path: str, target_sr: int = 32000) -> np.ndarray:
    """Read a WAV file to float32 mono at approximately target_sr.

    Uses stdlib `wave` (no soundfile dependency); nearest-neighbour resample
    is fine for verification purposes.
    """
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
        width = w.getsampwidth()
        channels = w.getnchannels()
    if width == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    if sr != target_sr and len(x) > 1:
        idx = np.linspace(0, len(x) - 1, int(len(x) * target_sr / sr)).astype(np.int64)
        x = x[idx]
    return x


class EnergyHeuristicBackend:
    """Fallback scorer: loud + high-frequency + bursty ⇒ distress-like."""
    name = "energy-heuristic (dev fallback)"

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        if audio.size < sr // 4:
            return 0.0
        rms = float(np.sqrt(np.mean(audio ** 2)))
        loudness = min(1.0, rms / 0.15)
        # spectral centroid — screams sit high
        spec = np.abs(np.fft.rfft(audio[: sr * 4]))
        freqs = np.fft.rfftfreq(min(len(audio), sr * 4), 1.0 / sr)
        centroid = float((spec * freqs).sum() / (spec.sum() + 1e-9))
        highness = min(1.0, max(0.0, (centroid - 400.0) / 1600.0))
        # burstiness — peak-to-mean envelope ratio
        env = np.abs(audio)
        win = max(1, sr // 50)
        env = env[: len(env) // win * win].reshape(-1, win).mean(axis=1)
        burst = min(1.0, (float(env.max()) / (float(env.mean()) + 1e-9)) / 8.0)
        return round(0.45 * loudness + 0.35 * highness + 0.20 * burst, 3)


class PannsBackend:
    """PANNs AudioSet tagging (requires panns-inference + torch)."""
    name = "PANNs"

    def __init__(self):
        from panns_inference import AudioTagging, labels  # noqa: import-heavy
        self._at = AudioTagging(checkpoint_path=None, device="cpu")
        self._labels = labels
        self._idx = [i for i, lbl in enumerate(labels)
                     if any(f in lbl.lower() for f in DISTRESS_LABELS)]
        log.info("PANNs loaded; %d distress-relevant classes", len(self._idx))

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        clip = audio[None, :].astype(np.float32)
        clipwise, _ = self._at.inference(clip)
        probs = clipwise[0]
        return round(float(min(1.0, sum(probs[i] for i in self._idx))), 3)


class YamnetBackend:
    """YAMNet AudioSet distress scoring (requires a TFLite runtime)."""
    name = "YAMNet"

    def __init__(self):
        from .yamnet_detector import YamnetDetector
        self._det = YamnetDetector()

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        return self._det.distress_score(audio, sr=sr)


class Stage2Verifier:
    def __init__(self, backend: Optional[object] = None):
        if backend is not None:
            self.backend = backend
            return
        for cls in (PannsBackend, YamnetBackend):
            try:
                self.backend = cls()
                return
            except Exception as exc:      # runtime not installed → next option
                log.warning("%s unavailable (%s)", cls.__name__, exc)
        log.warning("no ML backend available — using energy-heuristic fallback")
        self.backend = EnergyHeuristicBackend()

    def verify_wav(self, path: str) -> float:
        """Score a clip file 0.0..1.0 (1.0 = confident distress)."""
        try:
            audio = load_wav_mono(path)
        except Exception as exc:
            log.error("could not read clip %s: %s", path, exc)
            return 0.0
        return self.backend.score(audio)
