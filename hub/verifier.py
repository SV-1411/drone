"""Stage-2 audio verification with project-specific distress confirmation.

The legacy PANNs/YAMNet score remains available as a compatibility fallback,
but the Phase-2 path is preferred when the trained SVM artifact exists:
YAMNet representation + Phase-1 acoustic features -> RBF SVM -> temporal gate.
A single suspicious frame is never sufficient for a confirmed distress event.
"""
from __future__ import annotations

import logging
import os
import wave
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .acoustic_severity import calculate_acoustic_severity, summarize_feature_vector
from .audio_features import feature_dict
from .distress_classifier import DistressClassifier

log = logging.getLogger("hub.verifier")

DISTRESS_LABELS = ("scream", "shout", "yell", "crying", "wail", "groan", "whimper", "screaming")


def load_wav_mono(path: str, target_sr: int = 32000) -> np.ndarray:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
        width = w.getsampwidth()
        channels = w.getnchannels()
    if width == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported WAV sample width {width}")
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    if sr != target_sr and len(x) > 1:
        n = max(1, int(round(len(x) * target_sr / sr)))
        x = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(x)), x).astype(np.float32)
    return x


class EnergyHeuristicBackend:
    name = "energy-heuristic (dev fallback)"

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        if audio.size < sr // 4:
            return 0.0
        rms = float(np.sqrt(np.mean(audio ** 2)))
        loudness = min(1.0, rms / 0.15)
        n = min(len(audio), sr * 4)
        spec = np.abs(np.fft.rfft(audio[:n]))
        freqs = np.fft.rfftfreq(n, 1.0 / sr)
        centroid = float((spec * freqs).sum() / (spec.sum() + 1e-9))
        highness = min(1.0, max(0.0, (centroid - 400.0) / 1600.0))
        env = np.abs(audio)
        win = max(1, sr // 50)
        env = env[: len(env) // win * win].reshape(-1, win).mean(axis=1)
        burst = min(1.0, (float(env.max()) / (float(env.mean()) + 1e-9)) / 8.0)
        return round(0.45 * loudness + 0.35 * highness + 0.20 * burst, 3)


class PannsBackend:
    name = "PANNs"

    def __init__(self):
        from panns_inference import AudioTagging, labels
        self._at = AudioTagging(checkpoint_path=None, device="cpu")
        self._labels = labels
        self._idx = [i for i, lbl in enumerate(labels) if any(f in lbl.lower() for f in DISTRESS_LABELS)]

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        clipwise, _ = self._at.inference(audio[None, :].astype(np.float32))
        return round(float(min(1.0, sum(clipwise[0][i] for i in self._idx))), 3)


class YamnetBackend:
    name = "YAMNet"

    def __init__(self):
        from .yamnet_detector import YamnetDetector
        self._det = YamnetDetector()

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        return self._det.distress_score(audio, sr=sr)


@dataclass(frozen=True)
class VerificationResult:
    distress_confirmed: bool
    classifier_probability: float
    yamnet_distress_probability: float
    temporal_positive_frames: int
    temporal_frames: int
    temporal_gate_passed: bool
    acoustic_severity: float
    roughness: float
    rms_intensity: float
    spectral_score: float
    backend: str
    reason: str


class Stage2Verifier:
    """Project-specific verifier with a compatibility fallback."""

    def __init__(self, backend: Optional[object] = None, classifier: Optional[DistressClassifier] = None,
                 threshold: float = 0.70, min_positive_frames: int = 3):
        self.threshold = float(threshold)
        self.min_positive_frames = int(min_positive_frames)
        self.classifier = classifier
        self.project_backend = None
        try:
            self.classifier = self.classifier or DistressClassifier()
            from .yamnet_detector import YamnetDetector
            self.project_backend = YamnetDetector()
        except Exception as exc:
            log.warning("project distress model unavailable: %s", exc)
        if backend is not None:
            self.backend = backend
        elif self.project_backend is not None and self.classifier is not None:
            self.backend = self.project_backend
        else:
            self.backend = None
            for cls in (PannsBackend, YamnetBackend):
                try:
                    self.backend = cls()
                    break
                except Exception as exc:
                    log.warning("%s unavailable (%s)", cls.__name__, exc)
            if self.backend is None:
                self.backend = EnergyHeuristicBackend()

    @property
    def using_project_model(self) -> bool:
        return self.classifier is not None and self.project_backend is not None

    def _windows(self, audio: np.ndarray, sr: int) -> list[np.ndarray]:
        window = max(1, int(round(sr * 1.0)))
        hop = max(1, int(round(sr * 0.25)))
        if len(audio) <= window:
            return [np.pad(audio, (0, max(0, window - len(audio))))]
        starts = range(0, len(audio) - window + 1, hop)
        windows = [audio[s:s + window] for s in starts]
        if (len(audio) - window) % hop:
            windows.append(audio[-window:])
        return windows

    def _project_verify(self, audio: np.ndarray, sr: int) -> VerificationResult:
        assert self.classifier is not None and self.project_backend is not None
        windows = self._windows(audio, sr)
        positives = []
        probabilities = []
        for window in windows:
            rep = self.project_backend.embedding(window, sr)
            if rep is None:
                rep = self.project_backend.class_score_vector(window, sr)
            pred = self.classifier.predict_audio(window, sr, rep)
            p = float(pred.distress_probability)
            probabilities.append(p)
            positives.append(p >= self.threshold and pred.predicted_class == "distress")
        positive_count = sum(positives)
        confirmed = positive_count >= self.min_positive_frames
        temporal = positive_count / max(1, len(positives))
        full_features = feature_dict(audio, sr)
        rough, rms, spectral = summarize_feature_vector(full_features)
        yamnet_p = float(self.project_backend.distress_score(audio, sr))
        ml = float(max(probabilities) if probabilities else 0.0)
        severity = calculate_acoustic_severity(
            ml_confidence=ml,
            roughness=rough,
            rms_intensity=rms,
            spectral_score=spectral,
            temporal_persistence=temporal,
        )
        return VerificationResult(
            distress_confirmed=confirmed,
            classifier_probability=round(ml, 3),
            yamnet_distress_probability=round(yamnet_p, 3),
            temporal_positive_frames=positive_count,
            temporal_frames=len(positives),
            temporal_gate_passed=confirmed,
            acoustic_severity=severity.score,
            roughness=round(rough, 3),
            rms_intensity=round(rms, 3),
            spectral_score=round(spectral, 3),
            backend="yamnet_svm_acoustic",
            reason=severity.reasons,
        )

    def verify_wav_detail(self, path: str) -> VerificationResult:
        try:
            audio = load_wav_mono(path)
        except Exception as exc:
            log.error("could not read clip %s: %s", path, exc)
            return VerificationResult(False, 0.0, 0.0, 0, 0, False, 0.0, 0.0, 0.0, 0.0, "error", str(exc))
        if self.using_project_model:
            return self._project_verify(audio, 32000)
        score = float(self.backend.score(audio, 32000))
        return VerificationResult(
            distress_confirmed=score >= self.threshold,
            classifier_probability=score,
            yamnet_distress_probability=score if getattr(self.backend, "name", "") == "YAMNet" else 0.0,
            temporal_positive_frames=1 if score >= self.threshold else 0,
            temporal_frames=1,
            temporal_gate_passed=score >= self.threshold,
            acoustic_severity=round(score * 100.0, 1),
            roughness=0.0, rms_intensity=0.0, spectral_score=0.0,
            backend=getattr(self.backend, "name", type(self.backend).__name__),
            reason="compatibility fallback; train the Phase-2 model for project verification",
        )

    def verify_wav(self, path: str) -> float:
        """Backward-compatible score. Confirmed distress is zeroed on fallback/model rejection."""
        result = self.verify_wav_detail(path)
        if self.using_project_model and not result.distress_confirmed:
            return 0.0
        return round(result.classifier_probability, 3)
