"""Tests for the shared MFCC front-end (must stay in lockstep with firmware)."""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ml.mfcc import mfcc, N_FRAMES, N_MFCC, N_SAMPLES, SR


def test_output_shape():
    x = np.zeros(N_SAMPLES, dtype=np.float32)
    m = mfcc(x)
    assert m.shape == (N_FRAMES, N_MFCC)


def test_pad_and_crop():
    short = np.ones(1000, dtype=np.float32)
    long = np.ones(N_SAMPLES * 2, dtype=np.float32)
    assert mfcc(short).shape == (N_FRAMES, N_MFCC)
    assert mfcc(long).shape == (N_FRAMES, N_MFCC)


def test_deterministic():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.1, N_SAMPLES).astype(np.float32)
    assert np.allclose(mfcc(x), mfcc(x))


def test_tone_differs_from_silence():
    t = np.arange(N_SAMPLES) / SR
    tone = 0.5 * np.sin(2 * np.pi * 1200 * t).astype(np.float32)
    silence = np.zeros(N_SAMPLES, dtype=np.float32)
    assert not np.allclose(mfcc(tone), mfcc(silence))
    # a loud tone should raise the 0th coefficient (log energy) above silence
    assert mfcc(tone)[:, 0].mean() > mfcc(silence)[:, 0].mean()


def test_finite():
    rng = np.random.default_rng(2)
    for amp in (0.0, 1e-4, 0.5, 1.0):
        x = (amp * rng.normal(0, 1, N_SAMPLES)).astype(np.float32)
        assert np.all(np.isfinite(mfcc(x)))
