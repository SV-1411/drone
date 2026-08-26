"""Transparent acoustic severity scoring for confirmed distress events.

Severity is intentionally separate from detection. The classifier answers
"is this distress?"; this module estimates acoustic urgency after verification.
All inputs are normalized to 0..1 and the result is reported as 0..100.
"""
from __future__ import annotations

from dataclasses import dataclass


def _clip01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


@dataclass(frozen=True)
class AcousticSeverity:
    score: float
    ml_confidence: float
    roughness: float
    intensity: float
    spectral: float
    persistence: float
    reasons: str


def calculate_acoustic_severity(
    *,
    ml_confidence: float,
    roughness: float,
    rms_intensity: float,
    spectral_score: float,
    temporal_persistence: float,
) -> AcousticSeverity:
    """Calculate a transparent 0..100 acoustic severity score.

    Prototype weights are deliberately explicit for a final-year project:
    ML confidence 40%, roughness 20%, intensity 15%, spectral characteristics
    10%, temporal persistence 15%. This is an engineering score, not a medical
    or clinical severity scale.
    """
    ml = _clip01(ml_confidence)
    rough = _clip01(roughness)
    intensity = _clip01(rms_intensity)
    spectral = _clip01(spectral_score)
    persistence = _clip01(temporal_persistence)
    score01 = (
        0.40 * ml +
        0.20 * rough +
        0.15 * intensity +
        0.10 * spectral +
        0.15 * persistence
    )
    score = round(score01 * 100.0, 1)
    reasons = (
        f"ml={ml:.2f} rough={rough:.2f} intensity={intensity:.2f} "
        f"spectral={spectral:.2f} persistence={persistence:.2f}"
    )
    return AcousticSeverity(score, ml, rough, intensity, spectral, persistence, reasons)


def summarize_feature_vector(features: dict[str, float]) -> tuple[float, float, float]:
    """Map Phase-1 scalar features to severity-supporting 0..1 signals.

    This is intentionally conservative: these features support severity but do
    not independently decide distress.
    """
    rms = _clip01(features.get("rms_mean", 0.0) / 0.20)
    rough = _clip01(features.get("roughness_30_150", 0.0))
    centroid = float(features.get("spectral_centroid_mean", 0.0))
    spectral = _clip01((centroid - 500.0) / 2500.0)
    return rough, rms, spectral
