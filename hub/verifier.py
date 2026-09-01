"""Stage-2 PANN verification for the VanniKawachh sensing pipeline.

Stage 1 remains on the ESP32-S3 sensing node (MFCC + tiny CNN). The node
uploads the triggering audio clip to the Pi 5 after a Stage-1 hit. This
module is the Pi-5 Stage 2: PANNs/CNN14 scores distress-relevant AudioSet
classes over short windows and applies a temporal gate before the result is
accepted by the hub pipeline.

The PANN checkpoint is configurable with PANN_CHECKPOINT_PATH. This is
intended for the project's trained checkpoint on the Pi 5. If the variable
is empty, panns-inference resolves its standard checkpoint as a development
fallback; that fallback must not be described as the project's fine-tuned
model in benchmark results.
"""
from __future__ import annotations

import logging
import os
import wave
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger("hub.verifier")

DISTRESS_LABELS = (
    "scream", "shout", "yell", "crying", "wail", "groan", "whimper", "screaming"
)


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


class PannsBackend:
    """PANNs/CNN14 inference backend used by Stage 2 on the Pi 5."""

    name = "PANNs-CNN14"

    def __init__(self, checkpoint_path: str | None = None, device: str = "cpu"):
        from panns_inference import AudioTagging, labels

        self.checkpoint_path = checkpoint_path or os.environ.get("PANN_CHECKPOINT_PATH", "")
        self.device = device or os.environ.get("PANN_DEVICE", "cpu")
        self._at = AudioTagging(
            checkpoint_path=self.checkpoint_path or None,
            device=self.device,
        )
        self._labels = labels
        self._idx = [
            i for i, label in enumerate(labels)
            if any(fragment in label.lower() for fragment in DISTRESS_LABELS)
        ]
        if not self._idx:
            raise RuntimeError("PANN output labels contain no distress-relevant classes")
        log.info(
            "PANN Stage-2 loaded (%s), %d distress-relevant classes",
            self.checkpoint_path or "default checkpoint",
            len(self._idx),
        )

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        clipwise, _ = self._at.inference(audio[None, :].astype(np.float32))
        probs = np.asarray(clipwise[0], dtype=np.float32)
        return round(float(min(1.0, sum(float(probs[i]) for i in self._idx))), 3)


class YamnetBackend:
    """Small real-model fallback for cloud deployments without PANNs.

    Render ships the committed YAMNet TFLite model, but not the large PANN
    checkpoint or PyTorch runtime.  Keeping this as a learned AudioSet model
    avoids letting the development-only energy heuristic make dispatch
    decisions in the deployed service.
    """

    name = "YAMNet (AudioSet fallback)"

    def __init__(self):
        from .yamnet_detector import get_detector

        self._detector = get_detector()
        if self._detector is None:
            raise RuntimeError("YAMNet model or TFLite runtime is unavailable")

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        return self._detector.distress_score(audio, sr=sr)


class ProsodicStressBackend:
    """Stage-2 verifier for a short stressed spoken emergency call.

    This backend is evaluated only after PANN/YAMNet has not confirmed and
    only for a Stage-1 help/stressed-voice event. It measures the independent
    vocal-prosody evidence (F0, voiced duration, speech-band energy and SNR)
    on the uploaded clip; it is not a loudness-only fallback.
    """

    name = "prosodic stressed-speech verifier"

    def __init__(self, threshold: float = 0.55):
        self.threshold = float(threshold)
        self.last_result = None

    def score(self, audio: np.ndarray, sr: int = 32000) -> float:
        from .spoken_stress import analyse_spoken_stress

        self.last_result = analyse_spoken_stress(audio, sr=sr)
        return self.last_result.score if self.last_result.accepted else 0.0


class EnergyHeuristicBackend:
    """Development-only fallback when PANN cannot be loaded."""

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
    """PANN-first Stage-2 verifier with an explicit dev/test fallback."""

    def __init__(self, backend: Optional[object] = None,
                 threshold: float = 0.70, min_positive_frames: int = 3,
                 checkpoint_path: str | None = None, device: str = "cpu",
                 yamnet_threshold: float = 0.30,
                 yamnet_min_positive_frames: int = 3,
                 yamnet_single_strong_threshold: float = 0.75,
                 prosody_threshold: float = 0.55):
        self.threshold = float(threshold)
        self.min_positive_frames = max(1, int(min_positive_frames))
        self.prosody_backend = ProsodicStressBackend(prosody_threshold)
        self.yamnet_single_strong_threshold = float(yamnet_single_strong_threshold)
        if not 0.0 <= self.yamnet_single_strong_threshold <= 1.0:
            raise ValueError("yamnet_single_strong_threshold must be in [0, 1]")
        self._explicit_backend = backend is not None
        if backend is not None:
            self.backend = backend
        else:
            try:
                self.backend = PannsBackend(checkpoint_path=checkpoint_path, device=device)
            except Exception as exc:
                log.warning("PANN Stage-2 unavailable: %s", exc)
                try:
                    self.backend = YamnetBackend()
                    self.threshold = float(yamnet_threshold)
                    self.min_positive_frames = max(1, int(yamnet_min_positive_frames))
                    log.info(
                        "using YAMNet Stage-2 fallback (threshold %.2f, %d frames)",
                        self.threshold,
                        self.min_positive_frames,
                    )
                except Exception as yamnet_exc:
                    log.warning("YAMNet Stage-2 fallback unavailable: %s", yamnet_exc)
                    self.backend = EnergyHeuristicBackend()

    @property
    def using_panns(self) -> bool:
        return isinstance(self.backend, PannsBackend)

    def _windows(self, audio: np.ndarray, sr: int) -> list[np.ndarray]:
        window = max(1, int(round(sr * 1.0)))
        hop = max(1, int(round(sr * 0.25)))
        if len(audio) <= window:
            return [np.pad(audio, (0, max(0, window - len(audio))))]
        windows = [audio[s:s + window] for s in range(0, len(audio) - window + 1, hop)]
        if (len(audio) - window) % hop:
            windows.append(audio[-window:])
        return windows

    def _temporal_verify(self, audio: np.ndarray, sr: int) -> VerificationResult:
        windows = self._windows(audio, sr)
        scores = [float(self.backend.score(w, sr)) for w in windows]
        positives = [score >= self.threshold for score in scores]
        positive_count = sum(positives)
        score = float(max(scores) if scores else 0.0)
        # A muffled or interrupted distress cry can be shorter than the normal
        # three-window persistence gate.  On the cloud YAMNet fallback only,
        # one exceptionally strong learned AudioSet event is enough to verify
        # it.  This is deliberately not a loudness/DSP bypass: weaker YAMNet
        # evidence still needs the existing temporal confirmation, and PANN
        # keeps its original persistence policy.
        single_strong = bool(
            isinstance(self.backend, YamnetBackend)
            and score >= self.yamnet_single_strong_threshold
        )
        confirmed = single_strong or positive_count >= self.min_positive_frames
        persistence = positive_count / max(1, len(scores))
        return VerificationResult(
            distress_confirmed=confirmed,
            classifier_probability=round(score, 3),
            yamnet_distress_probability=0.0,
            temporal_positive_frames=positive_count,
            temporal_frames=len(scores),
            temporal_gate_passed=confirmed,
            acoustic_severity=round(score * 100.0, 1),
            roughness=0.0,
            rms_intensity=round(float(np.sqrt(np.mean(audio ** 2))), 3) if audio.size else 0.0,
            spectral_score=round(persistence, 3),
            backend=self.backend.name,
            reason=(
                f"{self.backend.name} score={score:.2f}; accepted as one strong learned window "
                f"at {self.yamnet_single_strong_threshold:.2f}."
                if single_strong else
                f"{self.backend.name} score={score:.2f}; {positive_count}/{len(scores)} windows "
                f"passed threshold {self.threshold:.2f}; required {self.min_positive_frames}."
            ),
        )

    def _prosody_verify(self, audio: np.ndarray, sr: int) -> VerificationResult:
        score = float(self.prosody_backend.score(audio, sr))
        detail = self.prosody_backend.last_result
        confirmed = score >= self.prosody_backend.threshold
        reason = detail.reasons if detail is not None else ()
        return VerificationResult(
            distress_confirmed=confirmed,
            classifier_probability=round(score, 3),
            yamnet_distress_probability=0.0,
            temporal_positive_frames=1 if confirmed else 0,
            temporal_frames=1,
            temporal_gate_passed=confirmed,
            acoustic_severity=round(score * 100.0, 1),
            roughness=0.0,
            rms_intensity=round(float(np.sqrt(np.mean(audio ** 2))), 3) if audio.size else 0.0,
            spectral_score=round(score, 3),
            backend=self.prosody_backend.name,
            reason=(f"prosodic score={score:.2f}; threshold {self.prosody_backend.threshold:.2f}; "
                    + "; ".join(reason)),
        )

    def verify_wav_detail(self, path: str, allow_spoken_stress: bool = False) -> VerificationResult:
        try:
            audio = load_wav_mono(path)
        except Exception as exc:
            log.error("could not read clip %s: %s", path, exc)
            return VerificationResult(False, 0.0, 0.0, 0, 0, False, 0.0, 0.0, 0.0, 0.0, "error", str(exc))

        # Explicit backends are retained for deterministic unit tests. Normal
        # production construction is PANN-first and therefore reaches this
        # path only with PANN unless loading failed.
        if self.using_panns or isinstance(self.backend, YamnetBackend) or self._explicit_backend:
            result = self._temporal_verify(audio, 32000)
            if result.distress_confirmed or not allow_spoken_stress:
                return result
            return self._prosody_verify(audio, 32000)

        score = float(self.backend.score(audio, 32000))
        return VerificationResult(
            distress_confirmed=False,
            classifier_probability=round(score, 3),
            yamnet_distress_probability=0.0,
            temporal_positive_frames=0,
            temporal_frames=1,
            temporal_gate_passed=False,
            acoustic_severity=0.0,
            roughness=0.0,
            rms_intensity=round(float(np.sqrt(np.mean(audio ** 2))), 3) if audio.size else 0.0,
            spectral_score=0.0,
            backend=self.backend.name,
            reason="PANN unavailable; development fallback cannot confirm a distress event.",
        )

    def verify_wav(self, path: str, allow_spoken_stress: bool = False) -> float:
        result = self.verify_wav_detail(path, allow_spoken_stress=allow_spoken_stress)
        return round(result.classifier_probability if result.distress_confirmed else 0.0, 3)
