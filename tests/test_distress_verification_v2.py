from __future__ import annotations

from hub.acoustic_severity import calculate_acoustic_severity


def _confirm(probs, threshold=0.70, minimum=3):
    run = best = 0
    for probability in probs:
        if probability >= threshold:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best >= minimum


def test_isolated_transient_does_not_confirm():
    assert not _confirm([0.10, 0.91, 0.12, 0.08])


def test_three_persistent_frames_confirm():
    assert _confirm([0.10, 0.81, 0.90, 0.86, 0.20])


def test_severity_is_bounded():
    low = calculate_acoustic_severity(
        ml_confidence=0.7, roughness=0.0, rms_intensity=0.0,
        spectral_score=0.0, temporal_persistence=0.0,
    )
    high = calculate_acoustic_severity(
        ml_confidence=1.0, roughness=1.0, rms_intensity=1.0,
        spectral_score=1.0, temporal_persistence=1.0,
    )
    assert 0.0 <= low.score <= 100.0
    assert 0.0 <= high.score <= 100.0
    assert high.score > low.score


def test_severity_weights_are_transparent():
    result = calculate_acoustic_severity(
        ml_confidence=1.0, roughness=1.0, rms_intensity=1.0,
        spectral_score=1.0, temporal_persistence=1.0,
    )
    assert result.score == 100.0
