"""Reproducible MFCC front-end shared by training, evaluation, and firmware.

Deployed ML only works if the features the ESP32 computes at run time match the
features the model trained on. To guarantee that, we do NOT use librosa's MFCC
(whose exact filterbank/DCT normalisation is awkward to reproduce in C).
Instead this file is the single definition; firmware/node/mfcc.h mirrors it
step for step, and tests/test_mfcc.py checks it.

Pipeline (16 kHz mono, 2.0 s window):
  pre-emphasis 0.97 -> frames (512 samples, hop 256, Hamming) -> |FFT|^2
  -> 40 triangular mel filters (0..8000 Hz) -> log(energy + 1e-6)
  -> DCT-II -> keep 13 coefficients.
Output shape: (num_frames, 13), num_frames = 1 + (N - 512) // 256.
"""
from __future__ import annotations

import numpy as np

SR = 16000
CLIP_S = 2.0
N_SAMPLES = int(SR * CLIP_S)
N_FFT = 512
HOP = 256
N_MELS = 40
N_MFCC = 13
PREEMPH = 0.97
EPS = 1e-6
N_FRAMES = 1 + (N_SAMPLES - N_FFT) // HOP


def _hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + f / 700.0)


def _mel_to_hz(m):
    return 700.0 * (10.0 ** (m / 2595.0) - 1.0)


def _mel_filterbank(sr=SR, n_fft=N_FFT, n_mels=N_MELS):
    """Triangular mel filters over the power-spectrum bins (n_fft//2 + 1)."""
    n_bins = n_fft // 2 + 1
    mel_min, mel_max = _hz_to_mel(0.0), _hz_to_mel(sr / 2.0)
    mel_pts = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_pts = _mel_to_hz(mel_pts)
    bin_pts = np.floor((n_fft + 1) * hz_pts / sr).astype(int)
    fb = np.zeros((n_mels, n_bins), dtype=np.float32)
    for m in range(1, n_mels + 1):
        l, c, r = bin_pts[m - 1], bin_pts[m], bin_pts[m + 1]
        for k in range(l, c):
            if c > l:
                fb[m - 1, k] = (k - l) / (c - l)
        for k in range(c, r):
            if r > c:
                fb[m - 1, k] = (r - k) / (r - c)
    return fb


def _dct_matrix(n_mfcc=N_MFCC, n_mels=N_MELS):
    """DCT-II basis (n_mfcc x n_mels)."""
    d = np.zeros((n_mfcc, n_mels), dtype=np.float32)
    for i in range(n_mfcc):
        for j in range(n_mels):
            d[i, j] = np.cos(np.pi * i * (2 * j + 1) / (2 * n_mels))
    return d


_HAMMING = (0.54 - 0.46 * np.cos(2 * np.pi * np.arange(N_FFT) / (N_FFT - 1))).astype(np.float32)
_FB = _mel_filterbank()
_DCT = _dct_matrix()


def mfcc(audio: np.ndarray) -> np.ndarray:
    """Compute the (N_FRAMES, N_MFCC) MFCC matrix from a mono float clip."""
    x = np.asarray(audio, dtype=np.float32)
    if len(x) < N_SAMPLES:
        x = np.pad(x, (0, N_SAMPLES - len(x)))
    else:
        x = x[:N_SAMPLES]
    x = np.concatenate([[x[0]], x[1:] - PREEMPH * x[:-1]]).astype(np.float32)
    out = np.zeros((N_FRAMES, N_MFCC), dtype=np.float32)
    for i in range(N_FRAMES):
        frame = x[i * HOP: i * HOP + N_FFT] * _HAMMING
        power = np.abs(np.fft.rfft(frame, n=N_FFT)) ** 2
        mel = np.log(_FB @ power + EPS)
        out[i] = _DCT @ mel
    return out
