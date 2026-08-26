"""Phase-2 project-specific distress classifier.

The classifier consumes the deterministic Phase-1 acoustic feature vector plus
YAMNet's learned class-score representation. When a compatible YAMNet export
provides a 1024-D embedding, that embedding is preferred automatically.

Training uses an RBF SVM with probability calibration enabled by scikit-learn.
The model is intentionally small and CPU-friendly for the final-year project.
"""
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from typing import Optional

import numpy as np

from hub.audio_features import FEATURE_NAMES, extract_features

CLASS_NAMES = ("background_noise", "normal_human", "distress")
DEFAULT_THRESHOLD = 0.70
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "distress_svm.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "distress_scaler.pkl")
PCA_PATH = os.path.join(MODEL_DIR, "distress_pca.pkl")
METADATA_PATH = os.path.join(MODEL_DIR, "distress_model_meta.pkl")


def _sklearn():
    try:
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.svm import SVC
        return Pipeline, StandardScaler, SVC
    except ImportError as exc:
        raise RuntimeError("Phase-2 classifier requires scikit-learn; install project requirements first") from exc


def build_feature_vector(audio: np.ndarray, sr: int, yamnet_representation: np.ndarray) -> np.ndarray:
    """Concatenate YAMNet representation and the fixed Phase-1 feature vector."""
    y = np.asarray(yamnet_representation, dtype=np.float32).reshape(-1)
    acoustic = extract_features(audio, sr).astype(np.float32)
    out = np.concatenate([y, acoustic]).astype(np.float32)
    if not np.isfinite(out).all():
        raise ValueError("non-finite classifier feature vector")
    return out


def train_classifier(X: np.ndarray, y: np.ndarray, *, C: float = 4.0, gamma: str | float = "scale"):
    """Fit a scaled RBF SVM and return the fitted sklearn Pipeline."""
    Pipeline, StandardScaler, SVC = _sklearn()
    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y)
    if X.ndim != 2 or y.ndim != 1 or len(X) != len(y):
        raise ValueError("X must be 2-D and y must be a matching 1-D vector")
    if len(np.unique(y)) < 2:
        raise ValueError("training data must contain at least two classes")
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("svm", SVC(kernel="rbf", C=C, gamma=gamma, probability=True, class_weight="balanced", random_state=42)),
    ])
    model.fit(X, y)
    return model


@dataclass
class DistressPrediction:
    distress_probability: float
    predicted_class: str
    probabilities: dict[str, float]


class DistressClassifier:
    """Load and run the trained Phase-2 SVM."""

    def __init__(self, model_path: str = MODEL_PATH):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"trained distress model not found: {model_path}. Run hub/train_distress_classifier.py first."
            )
        with open(model_path, "rb") as f:
            self._model = pickle.load(f)
        self.classes_ = tuple(str(x) for x in self._model.classes_)

    def predict_features(self, features: np.ndarray) -> DistressPrediction:
        x = np.asarray(features, dtype=np.float32).reshape(1, -1)
        if not np.isfinite(x).all():
            raise ValueError("non-finite inference features")
        probabilities = self._model.predict_proba(x)[0]
        pairs = {str(cls): float(prob) for cls, prob in zip(self._model.classes_, probabilities)}
        distress = float(pairs.get("distress", 0.0))
        predicted = str(self._model.classes_[int(np.argmax(probabilities))])
        return DistressPrediction(distress, predicted, pairs)

    def predict_audio(self, audio: np.ndarray, sr: int, yamnet_representation: np.ndarray) -> DistressPrediction:
        return self.predict_features(build_feature_vector(audio, sr, yamnet_representation))


def save_artifacts(model, metadata: dict, output_dir: str = MODEL_DIR) -> None:
    """Save the complete preprocessing/model artifact and feature metadata."""
    os.makedirs(output_dir, exist_ok=True)
    model_path = os.path.join(output_dir, "distress_svm.pkl")
    meta_path = os.path.join(output_dir, "distress_model_meta.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(meta_path, "wb") as f:
        pickle.dump(metadata, f, protocol=pickle.HIGHEST_PROTOCOL)
