"""Temporal confirmation gate for project-specific audio distress evidence."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

DEFAULT_THRESHOLD = 0.70
DEFAULT_MIN_POSITIVE_FRAMES = 3
DEFAULT_YAMNET_SUPPORT = 0.15


@dataclass(frozen=True)
class VerificationResult:
    distress_confirmed: bool
    classifier_probability: float
    yamnet_probability: float
    positive_frames: int
    temporal_gate_passed: bool
    yamnet_support_passed: bool
    threshold: float


class TemporalDistressVerifier:
    """Require persistent learned distress evidence before confirmation.

    A frame counts as positive only when the project-specific classifier exceeds
    the confidence threshold and the YAMNet distress score provides a small
    amount of supporting evidence. The latter is deliberately permissive: YAMNet
    is supporting evidence, not the final classifier.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        min_positive_frames: int = DEFAULT_MIN_POSITIVE_FRAMES,
        yamnet_support_threshold: float = DEFAULT_YAMNET_SUPPORT,
        history_size: int | None = None,
    ):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        if min_positive_frames < 1:
            raise ValueError("min_positive_frames must be >= 1")
        if not 0.0 <= yamnet_support_threshold <= 1.0:
            raise ValueError("yamnet_support_threshold must be in [0, 1]")
        self.threshold = float(threshold)
        self.min_positive_frames = int(min_positive_frames)
        self.yamnet_support_threshold = float(yamnet_support_threshold)
        self.history = deque(maxlen=history_size or max(3, min_positive_frames))

    def reset(self) -> None:
        self.history.clear()

    def update(self, classifier_probability: float, yamnet_probability: float) -> VerificationResult:
        svm = float(max(0.0, min(1.0, classifier_probability)))
        yam = float(max(0.0, min(1.0, yamnet_probability)))
        svm_positive = svm >= self.threshold
        yam_support = yam >= self.yamnet_support_threshold
        positive = svm_positive and yam_support
        self.history.append(positive)
        consecutive = 0
        for value in reversed(self.history):
            if not value:
                break
            consecutive += 1
        temporal_passed = consecutive >= self.min_positive_frames
        return VerificationResult(
            distress_confirmed=temporal_passed,
            classifier_probability=svm,
            yamnet_probability=yam,
            positive_frames=consecutive,
            temporal_gate_passed=temporal_passed,
            yamnet_support_passed=yam_support,
            threshold=self.threshold,
        )
