"""Phase-2 end-to-end audio distress verification facade."""
from __future__ import annotations

import numpy as np

from hub.distress_classifier import DistressClassifier, build_feature_vector
from hub.temporal_verifier import TemporalDistressVerifier, VerificationResult
from hub.yamnet_detector import YamnetDetector


class AudioDistressVerifier:
    """Combine the trained SVM, YAMNet support and temporal confirmation."""

    def __init__(
        self,
        classifier: DistressClassifier | None = None,
        yamnet: YamnetDetector | None = None,
        temporal: TemporalDistressVerifier | None = None,
    ):
        self.classifier = classifier or DistressClassifier()
        self.yamnet = yamnet
        self.temporal = temporal or TemporalDistressVerifier()

    def _representation(self, audio: np.ndarray, sr: int) -> np.ndarray:
        if self.yamnet is None:
            raise RuntimeError("AudioDistressVerifier requires a YAMNet detector")
        representation = self.yamnet.embedding(audio, sr)
        if representation is None:
            representation = self.yamnet.class_score_vector(audio, sr)
        return np.asarray(representation, dtype=np.float32).reshape(-1)

    def update(self, audio: np.ndarray, sr: int = 16000) -> dict:
        representation = self._representation(audio, sr)
        features = build_feature_vector(audio, sr, representation)
        prediction = self.classifier.predict_features(features)
        yamnet_score = self.yamnet.distress_score(audio, sr)
        temporal: VerificationResult = self.temporal.update(prediction.distress_probability, yamnet_score)
        return {
            "distress_confirmed": temporal.distress_confirmed,
            "classifier_probability": round(prediction.distress_probability, 4),
            "predicted_class": prediction.predicted_class,
            "class_probabilities": prediction.probabilities,
            "yamnet_distress_probability": round(float(yamnet_score), 4),
            "temporal_positive_frames": temporal.positive_frames,
            "temporal_gate_passed": temporal.temporal_gate_passed,
            "yamnet_support_passed": temporal.yamnet_support_passed,
            "threshold": temporal.threshold,
            "backend": "yamnet_project_svm",
        }

    def reset(self) -> None:
        self.temporal.reset()
