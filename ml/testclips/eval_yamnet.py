"""Score every test clip with the YAMNet detector and print top labels.
Run from repo root: .venv\\Scripts\\python.exe ml\\testclips\\eval_yamnet.py
"""
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from hub.yamnet_detector import get_detector  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    return x, sr


det = get_detector()
assert det is not None, "YAMNet failed to load"
for f in sorted(p for p in os.listdir(HERE) if p.endswith(".wav")):
    x, sr = read_wav(os.path.join(HERE, f))
    score, cls = det.distress_label(x, sr=sr)
    rms = float(np.sqrt(np.mean(x ** 2)))
    top = det.top_labels(x, sr=sr, k=4)
    print(f"{f:18s} rms={rms:.3f} distress={score:.3f} best={cls:15s} top={top}")
