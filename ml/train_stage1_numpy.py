"""Train the Stage-1 classifier with NumPy only (no TensorFlow required).

Why this exists: TensorFlow is a large download that some networks stall on.
This trainer needs only numpy + the stdlib, so the model can actually be
trained and exported in any environment. It uses a light feature set and a
small MLP that ports to the ESP32 as a few float matmuls (firmware branch
-DUSE_NN_STAGE1), with no TFLM library.

Features per 2 s clip: the shared MFCC (ml/mfcc.py), pooled over time into the
per-coefficient mean and standard deviation -> 26 numbers. Model: 26 -> 24
(ReLU) -> 4 (softmax). Trained with Adam and cross-entropy.

    python ml/train_stage1_numpy.py                 # trains on ml/data
    python ml/train_stage1_numpy.py --epochs 400

Outputs ml/out/stage1_nn.h (weights + normalisation, ready to #include in
firmware/node) and prints per-class validation accuracy.

The bootstrap dataset validates the pipeline only; retrain on real Phase-1
recordings for deployment (docs/HARDWARE_PHASES.md).
"""
from __future__ import annotations

import argparse
import os
import sys
import wave

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from ml.mfcc import mfcc as compute_mfcc, SR

DATA = os.path.join(_ROOT, "ml", "data")
OUT = os.path.join(_ROOT, "ml", "out")
CLASSES = ["background", "scream", "cry", "help"]
HIDDEN = 24


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        sr = w.getframerate(); n = w.getnframes()
        raw = w.readframes(n); ch = w.getnchannels(); sw = w.getsampwidth()
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR and len(x) > 1:
        idx = np.linspace(0, len(x) - 1, int(len(x) * SR / sr)).astype(np.int64)
        x = x[idx]
    return x


def features(audio: np.ndarray) -> np.ndarray:
    m = compute_mfcc(audio)                      # (frames, 13)
    return np.concatenate([m.mean(axis=0), m.std(axis=0)]).astype(np.float32)  # (26,)


def load(rng) -> tuple[np.ndarray, np.ndarray]:
    X, y = [], []
    for ci, cls in enumerate(CLASSES):
        cdir = os.path.join(DATA, cls)
        if not os.path.isdir(cdir):
            sys.exit(f"missing {cdir} - run: python ml/make_bootstrap_dataset.py")
        files = [f for f in os.listdir(cdir) if f.lower().endswith(".wav")]
        for f in files:
            a = read_wav(os.path.join(cdir, f))
            for g in (1.0, rng.uniform(0.5, 1.4), rng.uniform(0.7, 1.2)):
                aug = a * g + rng.normal(0, 0.003, len(a)).astype(np.float32)
                X.append(features(aug)); y.append(ci)
        print(f"[nn] {cls}: {len(files)} clips")
    return np.stack(X), np.array(y, dtype=np.int64)


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    X, y = load(rng)
    mu = X.mean(axis=0); sd = X.std(axis=0) + 1e-6
    Xn = (X - mu) / sd
    perm = rng.permutation(len(Xn))
    Xn, y = Xn[perm], y[perm]
    split = int(0.85 * len(Xn))
    Xtr, ytr, Xva, yva = Xn[:split], y[:split], Xn[split:], y[split:]
    print(f"[nn] features {X.shape}, classes {np.bincount(y)}")

    nin, nout = X.shape[1], len(CLASSES)
    W1 = (rng.standard_normal((nin, HIDDEN)) * np.sqrt(2.0 / nin)).astype(np.float32)
    b1 = np.zeros(HIDDEN, np.float32)
    W2 = (rng.standard_normal((HIDDEN, nout)) * np.sqrt(2.0 / HIDDEN)).astype(np.float32)
    b2 = np.zeros(nout, np.float32)
    params = [W1, b1, W2, b2]
    m = [np.zeros_like(p) for p in params]; v = [np.zeros_like(p) for p in params]
    lr, beta1, beta2, eps = 3e-3, 0.9, 0.999, 1e-8
    Y = np.eye(nout, dtype=np.float32)[ytr]

    for ep in range(1, args.epochs + 1):
        h_pre = Xtr @ W1 + b1
        h = np.maximum(0, h_pre)
        probs = softmax(h @ W2 + b2)
        # gradients (cross-entropy + softmax)
        dlogits = (probs - Y) / len(Xtr)
        gW2 = h.T @ dlogits; gb2 = dlogits.sum(0)
        dh = (dlogits @ W2.T) * (h_pre > 0)
        gW1 = Xtr.T @ dh; gb1 = dh.sum(0)
        grads = [gW1, gb1, gW2, gb2]
        for i, (p, g) in enumerate(zip(params, grads)):
            m[i] = beta1 * m[i] + (1 - beta1) * g
            v[i] = beta2 * v[i] + (1 - beta2) * g * g
            mh = m[i] / (1 - beta1 ** ep); vh = v[i] / (1 - beta2 ** ep)
            p -= lr * mh / (np.sqrt(vh) + eps)
        if ep % 50 == 0 or ep == args.epochs:
            tr_acc = (probs.argmax(1) == ytr).mean()
            vh = np.maximum(0, Xva @ W1 + b1) @ W2 + b2
            va_acc = (vh.argmax(1) == yva).mean()
            print(f"[nn] epoch {ep:4d}  train_acc {tr_acc:.3f}  val_acc {va_acc:.3f}")

    # per-class validation recall
    vpred = (np.maximum(0, Xva @ W1 + b1) @ W2 + b2).argmax(1)
    print("\n[nn] validation per-class recall:")
    for ci, cls in enumerate(CLASSES):
        mask = yva == ci
        if mask.any():
            print(f"     {cls:<12} {(vpred[mask] == ci).mean():.3f}  (n={int(mask.sum())})")

    os.makedirs(OUT, exist_ok=True)
    _export_c(os.path.join(OUT, "stage1_nn.h"), mu, sd, W1, b1, W2, b2)
    np.savez(os.path.join(OUT, "stage1_nn.npz"), mu=mu, sd=sd, W1=W1, b1=b1, W2=W2, b2=b2)
    print(f"\n[nn] exported ml/out/stage1_nn.h and .npz")
    print("[nn] bootstrap data validates the pipeline; retrain on real Phase-1 audio.")
    return 0


def _carr(name, a):
    a = np.asarray(a, dtype=np.float32).ravel()
    body = ", ".join(f"{x:.6f}f" for x in a)
    return f"static const float {name}[{a.size}] = {{ {body} }};"


def _export_c(path, mu, sd, W1, b1, W2, b2):
    nin, hid = W1.shape; nout = W2.shape[1]
    lines = [
        "// Auto-generated by ml/train_stage1_numpy.py — Stage-1 MLP for the node.",
        "// Features: MFCC pooled to per-coefficient mean+std (26), standardised,",
        "// then 26 -> %d (ReLU) -> %d (softmax). No external ML library needed." % (hid, nout),
        "#pragma once",
        f"#define S1NN_IN {nin}",
        f"#define S1NN_HID {hid}",
        f"#define S1NN_OUT {nout}",
        _carr("s1nn_mu", mu), _carr("s1nn_sd", sd),
        _carr("s1nn_W1", W1), _carr("s1nn_b1", b1),
        _carr("s1nn_W2", W2), _carr("s1nn_b2", b2),
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
