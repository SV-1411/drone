"""Render-safe, additive voice-distress decision layer.

The existing YAMNet/DSP/prosody paths remain valid evidence sources.  This
module adds a compact, fine-tuned TFLite classifier when the trained artifact
is installed.  It deliberately does *nothing dispatch-worthy* when that
artifact is absent: an untrained heuristic must never create a drone mission.

The exported model contract is documented by ``voice_distress_model_meta.json``:
input is a [1, 96, 64, 1] log-mel tensor and output probabilities use
VOICE_CLASSES in this exact order.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
import json
import os
import time
from typing import Protocol

import numpy as np

from .spoken_stress import analyse_spoken_stress

VOICE_CLASSES = (
    "distressed_speech",
    "scream",
    "cry_wail",
    "ordinary_voice",
    "background_interference",
)
DISTRESS_CLASSES = VOICE_CLASSES[:3]
SR = 16_000


def _resample(audio: np.ndarray, sr: int) -> np.ndarray:
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if sr == SR or x.size < 2:
        return x
    n = max(1, round(x.size * SR / sr))
    return np.interp(np.linspace(0, x.size - 1, n), np.arange(x.size), x).astype(np.float32)


def _mel_filterbank(n_fft: int = 512, bands: int = 64) -> np.ndarray:
    """Small dependency-free mel filterbank matching the training frontend."""
    def hz_to_mel(hz): return 2595.0 * np.log10(1.0 + hz / 700.0)
    def mel_to_hz(mel): return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)
    hz = mel_to_hz(np.linspace(hz_to_mel(20.0), hz_to_mel(SR / 2.0), bands + 2))
    bins = np.clip(np.floor((n_fft + 1) * hz / SR).astype(int), 0, n_fft // 2)
    bank = np.zeros((bands, n_fft // 2 + 1), dtype=np.float32)
    for i in range(bands):
        left, mid, right = bins[i:i + 3]
        if mid > left:
            bank[i, left:mid] = np.linspace(0.0, 1.0, mid - left, endpoint=False)
        if right > mid:
            bank[i, mid:right] = np.linspace(1.0, 0.0, right - mid, endpoint=False)
    return bank


_MEL = _mel_filterbank()


def log_mel(audio: np.ndarray, sr: int = SR) -> np.ndarray:
    """Return a deterministic 96x64 log-mel representation for TFLite."""
    x = _resample(audio, sr)
    target = SR * 2
    if x.size < target:
        x = np.pad(x, (0, target - x.size))
    elif x.size > target:
        x = x[-target:]
    frame, hop, n_fft = 400, 160, 512
    count = 1 + (x.size - frame) // hop
    frames = np.stack([x[i * hop:i * hop + frame] for i in range(count)])
    power = np.abs(np.fft.rfft(frames * np.hanning(frame), n=n_fft, axis=1)) ** 2
    mel = np.log(np.maximum(power @ _MEL.T, 1e-8)).astype(np.float32)
    # The 2 s frontend produces 198 frames.  Time-interpolate to a fixed
    # exportable model shape; this also makes short padded clips valid.
    idx = np.linspace(0, mel.shape[0] - 1, 96)
    lo = np.floor(idx).astype(int); hi = np.minimum(lo + 1, mel.shape[0] - 1)
    frac = (idx - lo)[:, None]
    return (mel[lo] * (1.0 - frac) + mel[hi] * frac).astype(np.float32)


@dataclass(frozen=True)
class VoiceQuality:
    speech_activity: bool
    snr_db: float
    muffled: bool
    whisper_like: bool
    rms: float

    def public(self) -> dict:
        return asdict(self)


def analyse_quality(audio: np.ndarray, sr: int = SR) -> VoiceQuality:
    """Describe signal conditions without using them as a rejection gate."""
    x = _resample(audio, sr)
    if x.size < 400:
        return VoiceQuality(False, 0.0, False, False, 0.0)
    frame, hop = 400, 160
    rms = np.asarray([np.sqrt(np.mean(x[i:i + frame] ** 2) + 1e-12)
                      for i in range(0, x.size - frame + 1, hop)])
    floor = float(np.percentile(rms, 20)) if rms.size else 0.0
    peak = float(rms.max()) if rms.size else 0.0
    snr = 20.0 * np.log10((peak + 1e-8) / (floor + 1e-8))
    activity = bool(peak >= 0.0015 and np.count_nonzero(rms >= max(0.0015, floor * 1.6, peak * .22)) >= 3)
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) ** 2
    freq = np.fft.rfftfreq(x.size, 1.0 / SR)
    low = float(spec[(freq >= 150) & (freq < 1500)].sum()) + 1e-9
    high = float(spec[(freq >= 2500) & (freq < 7000)].sum()) + 1e-9
    muffled = bool(activity and high / low < 0.045)
    # It is intentionally only a diagnostic tag.  The trained model, not this
    # rule, decides whether a quiet unvoiced utterance is distress.
    stress = analyse_spoken_stress(x, SR)
    whisper_like = bool(activity and not stress.accepted and stress.peak_pitch_hz <= 0.0)
    return VoiceQuality(activity, round(float(snr), 2), muffled, whisper_like,
                        round(float(np.sqrt(np.mean(x * x))), 6))


class ProbabilityBackend(Protocol):
    available: bool
    model_version: str
    def probabilities(self, audio: np.ndarray, sr: int = SR) -> dict[str, float]: ...


class TfliteVoiceBackend:
    """Lazy TFLite model loader.  No TensorFlow/Torch dependency is required."""
    def __init__(self, model_path: str = "", metadata_path: str = ""):
        self.available = False
        self.model_version = "voice-distress-unavailable"
        self._interp = None
        self._in_idx = self._out_idx = None
        self._in_detail = self._out_detail = None
        model_path = model_path or os.environ.get(
            "VOICE_DISTRESS_MODEL", os.path.join(os.path.dirname(__file__), "models", "voice_distress.tflite")
        )
        metadata_path = metadata_path or os.path.splitext(model_path)[0] + "_meta.json"
        if not os.path.exists(model_path):
            return
        try:
            try:
                from ai_edge_litert.interpreter import Interpreter
            except ImportError:
                from tensorflow.lite import Interpreter  # local training/dev only
            self._interp = Interpreter(model_path=model_path)
            self._interp.allocate_tensors()
            self._in_detail = self._interp.get_input_details()[0]
            self._out_detail = self._interp.get_output_details()[0]
            self._in_idx = self._in_detail["index"]
            self._out_idx = self._out_detail["index"]
            if os.path.exists(metadata_path):
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)
                classes = tuple(metadata.get("classes", VOICE_CLASSES))
                if classes != VOICE_CLASSES:
                    raise RuntimeError("voice distress model class order does not match the runtime contract")
                self.model_version = str(metadata.get("version", "voice-distress-v1"))
            else:
                self.model_version = "voice-distress-v1"
            self.available = True
        except Exception:
            self._interp = None

    def probabilities(self, audio: np.ndarray, sr: int = SR) -> dict[str, float]:
        if not self.available or self._interp is None:
            return {name: 0.0 for name in VOICE_CLASSES}
        x = log_mel(audio, sr)[None, :, :, None].astype(np.float32)
        detail = self._in_detail
        if detail["dtype"] == np.int8:
            scale, zero = detail["quantization"]
            if not scale:
                raise RuntimeError("quantized voice model input is missing a scale")
            x = np.clip(np.rint(x / scale + zero), -128, 127).astype(np.int8)
        self._interp.set_tensor(self._in_idx, x)
        self._interp.invoke()
        raw = self._interp.get_tensor(self._out_idx)
        if self._out_detail["dtype"] == np.int8:
            scale, zero = self._out_detail["quantization"]
            if not scale:
                raise RuntimeError("quantized voice model output is missing a scale")
            out = (np.asarray(raw, dtype=np.float32) - zero) * scale
        else:
            out = np.asarray(raw, dtype=np.float32)
        out = out.reshape(-1)
        if out.size != len(VOICE_CLASSES):
            raise RuntimeError("voice distress model output must contain five classes")
        if not np.isclose(float(out.sum()), 1.0, atol=.05):
            e = np.exp(out - out.max()); out = e / e.sum()
        return {name: round(float(max(0.0, value)), 5) for name, value in zip(VOICE_CLASSES, out)}


@dataclass(frozen=True)
class VoiceDecision:
    candidate: bool
    distress_confirmed: bool
    event_type: str
    confidence: float
    probabilities: dict[str, float]
    quality: VoiceQuality
    decision_path: str
    model_version: str
    reasons: tuple[str, ...]

    def public(self) -> dict:
        result = asdict(self)
        result["quality"] = self.quality.public()
        return result


class VoiceDecisionEngine:
    """Calibrated one-strong/two-moderate event aggregation per browser session."""
    def __init__(self, backend: ProbabilityBackend | None = None, *, strong: float = .90,
                 moderate: float = .65, keyword_moderate: float = .55):
        self.backend = backend or TfliteVoiceBackend()
        self.strong = float(strong)
        self.moderate = float(moderate)
        self.keyword_moderate = float(keyword_moderate)
        self._history: dict[str, deque[tuple[float, str, float]]] = defaultdict(lambda: deque(maxlen=8))

    def analyse(self, audio: np.ndarray, *, sr: int = SR, session_id: str = "single",
                keyword: str | None = None) -> VoiceDecision:
        quality = analyse_quality(audio, sr)
        legacy = analyse_spoken_stress(_resample(audio, sr), SR)
        probabilities = self.backend.probabilities(audio, sr)
        event, score = max(((name, float(probabilities.get(name, 0.0))) for name in DISTRESS_CLASSES),
                           key=lambda pair: pair[1])
        now = time.monotonic()
        history = self._history[str(session_id)]
        while history and now - history[0][0] > 1.5:
            history.popleft()
        if self.backend.available and score >= self.moderate:
            history.append((now, event, score))
        matches = sum(1 for _, old_event, old_score in history
                      if old_event == event and old_score >= self.moderate)
        keyword_supported = bool(keyword and (legacy.accepted or
                                  (self.backend.available and event == "distressed_speech" and score >= self.keyword_moderate)))
        strong = bool(self.backend.available and score >= self.strong)
        moderate_pair = bool(self.backend.available and matches >= 2)
        confirmed = strong or moderate_pair or keyword_supported
        if keyword_supported:
            path = "keyword+prosody" if legacy.accepted else "keyword+model"
        elif strong:
            path = f"single-strong-{event}"
        elif moderate_pair:
            path = f"two-window-{event}"
        else:
            path = "observed-not-confirmed"
        reasons = [f"top model class {event}={score:.0%}", f"quality: snr={quality.snr_db:.1f}dB"]
        if quality.muffled: reasons.append("muffled signal retained for model evaluation")
        if quality.whisper_like: reasons.append("whisper-like signal retained without an F0 rejection")
        if not self.backend.available:
            reasons.append("trained TFLite voice model is not installed; legacy routes remain active")
        return VoiceDecision(bool(score >= self.moderate or keyword), confirmed,
                             event if confirmed else "none", round(score, 4), probabilities,
                             quality, path, self.backend.model_version, tuple(reasons))
