from __future__ import annotations

import numpy as np

from hub.distress_classifier import CLASS_NAMES, train_classifier


def test_rbf_classifier_trains_and_returns_probabilities():
    rng = np.random.default_rng(42)
    X = np.vstack([
        rng.normal(-2.0, 0.25, (12, 16)),
        rng.normal(0.0, 0.25, (12, 16)),
        rng.normal(2.0, 0.25, (12, 16)),
    ]).astype(np.float32)
    y = np.asarray([
        CLASS_NAMES[0] for _ in range(12)
    ] + [
        CLASS_NAMES[1] for _ in range(12)
    ] + [
        CLASS_NAMES[2] for _ in range(12)
    ])
    model = train_classifier(X, y)
    probabilities = model.predict_proba(X[:4])
    assert probabilities.shape == (4, 3)
    assert np.isfinite(probabilities).all()
    assert np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-6)
