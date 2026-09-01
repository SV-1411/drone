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


# ---------------------------------------------------------------------------
# Stress-specific acoustic features for adaptive baseline detection
# ---------------------------------------------------------------------------


def _extract_f0(audio: np.ndarray, sr: int = SR, fmin: float = 60.0,
                 fmax: float = 600.0) -> float:
    """Median fundamental frequency via autocorrelation (Hz).  Returns 0 when
    no voiced frames are detected."""
    frame_len = int(0.025 * sr)
    hop_len = int(0.010 * sr)
    if audio.size < frame_len:
        return 0.0
    f0_values: list[float] = []
    for start in range(0, audio.size - frame_len + 1, hop_len):
        frame = audio[start:start + frame_len]
        windowed = frame * np.hanning(frame_len)
        ac = np.correlate(windowed, windowed, mode="full")
        ac = ac[ac.size // 2:]
        min_lag = max(1, int(sr / fmax))
        max_lag = min(int(sr / fmin), ac.size - 1)
        if max_lag <= min_lag:
            continue
        ac_range = ac[min_lag:max_lag]
        if ac_range.size == 0:
            continue
        peak_idx = int(np.argmax(ac_range)) + min_lag
        if ac[peak_idx] > 0.3 * ac[0]:
            f0_values.append(sr / peak_idx)
    return float(np.median(f0_values)) if f0_values else 0.0


def _extract_spectral_centroid(audio: np.ndarray, sr: int = SR) -> float:
    """Spectral centre of mass in Hz."""
    if audio.size < 256:
        return 0.0
    windowed = audio * np.hanning(audio.size)
    fft_mag = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(audio.size, 1.0 / sr)
    total = float(np.sum(fft_mag))
    if total < 1e-8:
        return 0.0
    return float(np.sum(freqs * fft_mag) / total)


def _extract_hnr(audio: np.ndarray, sr: int = SR, fmin: float = 60.0,
                 fmax: float = 600.0) -> float:
    """Harmonics-to-noise ratio in dB via autocorrelation.

    Uses the minimum autocorrelation in the pitch range as the noise floor
    rather than the mean of all lags (which breaks for loud periodic audio
    where non-harmonic lags are near zero).
    """
    frame_len = int(0.025 * sr)
    if audio.size < frame_len:
        return 0.0
    hnr_values: list[float] = []
    for start in range(0, audio.size - frame_len + 1, frame_len):
        frame = audio[start:start + frame_len]
        windowed = frame * np.hanning(frame_len)
        ac = np.correlate(windowed, windowed, mode="full")
        ac = ac[ac.size // 2:]
        if ac[0] < 1e-8:
            continue
        min_lag = max(1, int(sr / fmax))
        max_lag = min(int(sr / fmin), ac.size - 1)
        if max_lag <= min_lag:
            continue
        pitch_range = ac[min_lag:max_lag]
        if pitch_range.size == 0:
            continue
        harmonic_peak = float(np.max(pitch_range))
        # Noise floor: 10th percentile of the full autocorrelation (lags 1+)
        # excluding the pitch range. This avoids the harmonic peaks inflating
        # the noise estimate.
        non_pitch_mask = np.ones(ac.size - 1, dtype=bool)
        non_pitch_mask[min_lag - 1:max_lag - 1] = False
        non_pitch_ac = ac[1:][non_pitch_mask]
        if non_pitch_ac.size == 0:
            noise_energy = float(np.mean(ac[1:]))
        else:
            noise_energy = float(np.percentile(non_pitch_ac, 10))
        if noise_energy < 1e-8:
            # Very clean signal — use harmonic peak vs energy ratio.
            ratio = harmonic_peak / max(ac[0], 1e-8)
            hnr_values.append(min(10.0 * np.log10(max(ratio, 1e-8)), 30.0))
            continue
        hnr_values.append(10.0 * np.log10(
            max(harmonic_peak, 1e-8) / max(noise_energy, 1e-8)))
    return float(np.median(hnr_values)) if hnr_values else 0.0


@dataclass(frozen=True)
class VoiceQuality:
    speech_activity: bool
    snr_db: float
    muffled: bool
    whisper_like: bool
    rms: float

    def public(self) -> dict:
        return asdict(self)


# Population-level thresholds for normal adult speech.
# Used as fallback when per-session calibration itself shows stress.
NORMAL_F0_CEILING = 260.0        # Hz - upper end of typical adult female range
NORMAL_CENTROID_CEILING = 2800.0 # Hz - typical speech centroid ceiling
NORMAL_HNR_FLOOR = 10.0          # dB - below this = breathy/strained


@dataclass(frozen=True)
class BaselineResult:
    """Adaptive baseline deviations for speaker-independent stress detection."""
    calibrated: bool
    calibration_alert: bool  # True when calibration data itself exceeds normal thresholds
    f0_deviation: float
    centroid_deviation: float
    hnr_deviation: float
    baseline_f0: float
    baseline_centroid: float
    baseline_hnr: float
    stress_score: float

    def public(self) -> dict:
        return asdict(self)


@dataclass
class VoiceBaseline:
    """Per-session adaptive baseline for speaker-independent stress detection.

    During the first *calibration_windows* windows the baseline records the
    speaker's "normal" voice profile (median F0, spectral centroid, HNR).
    After calibration each new window is scored against that baseline; the
    resulting ``stress_score`` (0–1) rises when the voice deviates in a
    stress-consistent direction (elevated pitch, brighter spectrum, more
    breathiness).
    """
    calibration_windows: int = 3
    _windows_seen: int = 0
    _f0_samples: list = None  # type: ignore[assignment]
    _centroid_samples: list = None  # type: ignore[assignment]
    _hnr_samples: list = None  # type: ignore[assignment]
    _calibrated: bool = False
    _calibration_alert: bool = False
    _baseline_f0: float = 0.0
    _baseline_centroid: float = 0.0
    _baseline_hnr: float = 0.0

    def __post_init__(self):
        if self._f0_samples is None:
            object.__setattr__(self, '_f0_samples', [])
            object.__setattr__(self, '_centroid_samples', [])
            object.__setattr__(self, '_hnr_samples', [])

    @property
    def calibrated(self) -> bool:
        return self._calibrated

    @property
    def calibration_alert(self) -> bool:
        return self._calibration_alert

    def update_and_score(self, audio: np.ndarray, sr: int = SR) -> BaselineResult:
        """Feed a new window; return baseline deviations (zeroed while calibrating)."""
        f0 = _extract_f0(audio, sr)
        centroid = _extract_spectral_centroid(audio, sr)
        hnr = _extract_hnr(audio, sr)

        self._windows_seen += 1

        if not self._calibrated:
            if f0 > 0:
                self._f0_samples.append(f0)
            if centroid > 0:
                self._centroid_samples.append(centroid)
            if hnr > 0:
                self._hnr_samples.append(hnr)
            if self._windows_seen >= self.calibration_windows:
                self._calibrate()
            return BaselineResult(False, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        # --- Post-calibration scoring ---
        #
        # Two paths:
        #   1. calibration_alert = True  -> the calibration data itself exceeded
        #      normal speech thresholds, so the entire clip is likely distressed.
        #      Score using absolute thresholds (no deviation needed).
        #   2. calibration_alert = False -> normal calibration; score using
        #      per-session deviation from baseline.

        if self._calibration_alert:
            # Absolute-threshold scoring: how far above normal speech ranges?
            f0_score = float(np.clip(
                (self._baseline_f0 - NORMAL_F0_CEILING) / NORMAL_F0_CEILING, 0, 1))
            cent_score = float(np.clip(
                (self._baseline_centroid - NORMAL_CENTROID_CEILING) / NORMAL_CENTROID_CEILING, 0, 1))
            hnr_score = float(np.clip(
                (NORMAL_HNR_FLOOR - self._baseline_hnr) / NORMAL_HNR_FLOOR, 0, 1))
            # Also factor in per-window features for additional signal.
            win_f0_score = 0.0
            if f0 > NORMAL_F0_CEILING:
                win_f0_score = float(np.clip(
                    (f0 - NORMAL_F0_CEILING) / NORMAL_F0_CEILING, 0, 1))
            win_cent_score = 0.0
            if centroid > NORMAL_CENTROID_CEILING:
                win_cent_score = float(np.clip(
                    (centroid - NORMAL_CENTROID_CEILING) / NORMAL_CENTROID_CEILING, 0, 1))
            # Blend calibration-based (60%) with window-specific (40%).
            cal_weight = 0.60
            win_weight = 0.40
            stress_score = cal_weight * (0.50 * f0_score + 0.25 * cent_score + 0.25 * hnr_score)
            stress_score += win_weight * (0.50 * win_f0_score + 0.25 * win_cent_score + 0.25 * hnr_score)
            return BaselineResult(
                calibrated=True,
                calibration_alert=True,
                f0_deviation=0.0,  # deviation not meaningful in alert mode
                centroid_deviation=0.0,
                hnr_deviation=0.0,
                baseline_f0=round(self._baseline_f0, 1),
                baseline_centroid=round(self._baseline_centroid, 1),
                baseline_hnr=round(self._baseline_hnr, 1),
                stress_score=round(stress_score, 4),
            )

        # Standard deviation-based scoring.
        f0_dev = 0.0
        if self._baseline_f0 > 0 and f0 > 0:
            f0_dev = (f0 - self._baseline_f0) / self._baseline_f0
        centroid_dev = 0.0
        if self._baseline_centroid > 0 and centroid > 0:
            centroid_dev = (centroid - self._baseline_centroid) / self._baseline_centroid
        hnr_dev = 0.0
        if self._baseline_hnr > 0 and hnr > 0:
            hnr_dev = (hnr - self._baseline_hnr) / self._baseline_hnr

        # Weighted stress score: F0 strongest indicator.
        f0_score = float(np.clip(f0_dev / 0.30, 0, 1))
        centroid_score = float(np.clip(centroid_dev / 0.20, 0, 1))
        hnr_score = float(np.clip(-hnr_dev / 0.30, 0, 1))
        stress_score = 0.50 * f0_score + 0.25 * centroid_score + 0.25 * hnr_score

        return BaselineResult(
            calibrated=True,
            calibration_alert=False,
            f0_deviation=round(f0_dev, 4),
            centroid_deviation=round(centroid_dev, 4),
            hnr_deviation=round(hnr_dev, 4),
            baseline_f0=round(self._baseline_f0, 1),
            baseline_centroid=round(self._baseline_centroid, 1),
            baseline_hnr=round(self._baseline_hnr, 1),
            stress_score=round(stress_score, 4),
        )

    # ------------------------------------------------------------------
    def _calibrate(self) -> None:
        self._baseline_f0 = float(np.median(self._f0_samples)) if self._f0_samples else 0.0
        self._baseline_centroid = float(np.median(self._centroid_samples)) if self._centroid_samples else 0.0
        self._baseline_hnr = float(np.median(self._hnr_samples)) if self._hnr_samples else 0.0
        # Check if calibration data itself exceeds normal speech thresholds.
        alert = (
            self._baseline_f0 > NORMAL_F0_CEILING
            or self._baseline_centroid > NORMAL_CENTROID_CEILING
            or (0 < self._baseline_hnr < NORMAL_HNR_FLOOR)
        )
        object.__setattr__(self, '_calibration_alert', alert)
        object.__setattr__(self, '_calibrated', True)


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


# Sentinel for windows that arrive before calibration completes.
_BASELINE_EMPTY = BaselineResult(False, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


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
    baseline: BaselineResult
    decision_path: str
    model_version: str
    reasons: tuple[str, ...]

    def public(self) -> dict:
        result = asdict(self)
        result["quality"] = self.quality.public()
        result["baseline"] = self.baseline.public()
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
        self._baselines: dict[str, VoiceBaseline] = defaultdict(VoiceBaseline)

    def analyse(self, audio: np.ndarray, *, sr: int = SR, session_id: str = "single",
                keyword: str | None = None) -> VoiceDecision:
        quality = analyse_quality(audio, sr)
        legacy = analyse_spoken_stress(_resample(audio, sr), SR)
        probabilities = self.backend.probabilities(audio, sr)

        # Adaptive baseline: tracks the speaker's "normal" profile per session.
        baseline = self._baselines[str(session_id)]
        baseline_result = baseline.update_and_score(audio, sr)

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

        # Adaptive baseline detection paths.
        # Path A: calibration_alert — calibration data itself exceeded normal
        # speech thresholds, so use a lower threshold (0.50) since the absolute
        # evidence is strong.
        # Path B: standard deviation — calibration was normal but later windows
        # deviate; use 0.70 threshold.
        cal_alert_threshold = 0.50 if baseline_result.calibration_alert else 0.70
        baseline_confirmed = bool(
            baseline_result.calibrated
            and baseline_result.stress_score >= cal_alert_threshold
            and not self.backend.available
        )
        baseline_boost = bool(
            baseline_result.calibrated
            and baseline_result.stress_score >= (cal_alert_threshold - 0.10)
            and self.backend.available
            and score >= self.moderate
            and not strong
            and not moderate_pair
        )

        confirmed = strong or moderate_pair or keyword_supported or baseline_confirmed or baseline_boost
        if keyword_supported:
            path = "keyword+prosody" if legacy.accepted else "keyword+model"
        elif strong:
            path = f"single-strong-{event}"
        elif moderate_pair:
            path = f"two-window-{event}"
        elif baseline_boost:
            path = f"model+baseline-{event}"
        elif baseline_confirmed:
            path = f"baseline-{event}"
        else:
            path = "observed-not-confirmed"
        reasons = [f"top model class {event}={score:.0%}", f"quality: snr={quality.snr_db:.1f}dB"]
        if baseline_result.calibrated:
            if baseline_result.calibration_alert:
                reasons.append(
                    f"baseline-alert: f0={baseline_result.baseline_f0:.0f}Hz "
                    f"cent={baseline_result.baseline_centroid:.0f}Hz "
                    f"hnr={baseline_result.baseline_hnr:.1f}dB "
                    f"stress={baseline_result.stress_score:.0%}")
            else:
                reasons.append(
                    f"baseline: f0={baseline_result.f0_deviation:+.0%} "
                    f"centroid={baseline_result.centroid_deviation:+.0%} "
                    f"hnr={baseline_result.hnr_deviation:+.0%} "
                    f"stress={baseline_result.stress_score:.0%}")
        if quality.muffled: reasons.append("muffled signal retained for model evaluation")
        if quality.whisper_like: reasons.append("whisper-like signal retained without an F0 rejection")
        if not self.backend.available:
            if baseline_result.calibrated:
                reasons.append("TFLite model absent; adaptive baseline active")
            else:
                reasons.append("trained TFLite voice model is not installed; legacy routes remain active")
        return VoiceDecision(bool(score >= self.moderate or keyword), confirmed,
                             event if confirmed else "none", round(score, 4), probabilities,
                             quality, baseline_result, path, self.backend.model_version,
                             tuple(reasons))
