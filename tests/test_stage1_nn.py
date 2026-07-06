"""Validate the deployed Stage-1 inference path (the logic firmware mirrors).

Skips cleanly if the trained model / dataset are absent (both are gitignored
artifacts produced by ml/train_stage1_numpy.py + ml/make_bootstrap_dataset.py).
"""
from __future__ import annotations

import os
import sys
import wave

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ml import infer_nn
from ml.infer_nn import CLASSES, Stage1NN
from ml.mfcc import SR

DATA = os.path.join(ROOT, "ml", "data")

pytestmark = pytest.mark.skipif(
    not infer_nn.available() or not os.path.isdir(DATA),
    reason="trained model / bootstrap dataset not present (run ml/ scripts first)",
)


def _read(path):
    with wave.open(path, "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def test_deployed_path_separates_classes():
    """The pooled-MLP path (what the ESP32 runs) should classify the bootstrap
    clips well and, crucially, not fire 'background' as a distress class."""
    nn = Stage1NN()
    total = correct = bg_false = bg_total = 0
    for ci, cls in enumerate(CLASSES):
        cdir = os.path.join(DATA, cls)
        if not os.path.isdir(cdir):
            continue
        for f in sorted(os.listdir(cdir))[:40]:
            if not f.endswith(".wav"):
                continue
            k, _ = nn.infer(_read(os.path.join(cdir, f)))
            total += 1
            correct += (k == ci)
            if cls == "background":
                bg_total += 1
                bg_false += (k != 0)
    assert total > 0
    assert correct / total > 0.9                     # pipeline validation
    if bg_total:
        assert bg_false / bg_total < 0.1             # low false-trigger on noise


def test_confidence_in_range():
    nn = Stage1NN()
    x = np.zeros(int(SR * 2.0), dtype=np.float32)
    k, p = nn.infer(x)
    assert 0.0 <= p <= 1.0 and 0 <= k < len(CLASSES)
