"""Reference inference for the NumPy-trained Stage-1 MLP.

This mirrors, step for step, what firmware/node/stage1.cpp does in the
-DUSE_NN_STAGE1 branch: MFCC -> pool to per-coefficient mean+std -> standardise
-> 26->24 ReLU -> 4 softmax. It exists so the deployed C path can be checked in
Python (tests/test_stage1_nn.py) and used by eval without TensorFlow.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from ml.mfcc import mfcc as compute_mfcc

CLASSES = ["background", "scream", "cry", "help"]
_MODEL = os.path.join(_ROOT, "ml", "out", "stage1_nn.npz")


class Stage1NN:
    def __init__(self, path: str = _MODEL):
        d = np.load(path)
        self.mu, self.sd = d["mu"], d["sd"]
        self.W1, self.b1, self.W2, self.b2 = d["W1"], d["b1"], d["W2"], d["b2"]

    def features(self, audio: np.ndarray) -> np.ndarray:
        m = compute_mfcc(audio)
        # population std (ddof=0), same as the firmware's var/N
        return np.concatenate([m.mean(axis=0), m.std(axis=0)]).astype(np.float32)

    def infer(self, audio: np.ndarray) -> tuple[int, float]:
        x = (self.features(audio) - self.mu) / self.sd
        h = np.maximum(0, x @ self.W1 + self.b1)
        z = h @ self.W2 + self.b2
        z = z - z.max()
        p = np.exp(z) / np.exp(z).sum()
        k = int(p.argmax())
        return k, float(p[k])


def available() -> bool:
    return os.path.exists(_MODEL)
