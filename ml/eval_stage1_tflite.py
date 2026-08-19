"""Evaluate the exported int8 Stage-1 model (ml/out/stage1_int8.tflite).

This tests the ACTUAL artifact that ships to the ESP32 -- the quantized
TFLite flatbuffer -- not the float Keras model it was converted from.
Feeds it 2 s windows from WAV files and prints per-class probabilities.

    python ml/eval_stage1_tflite.py ml/testclips/*.wav
    python ml/eval_stage1_tflite.py --dir ml/data/scream
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import wave

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from ml.mfcc import mfcc as compute_mfcc, SR, N_SAMPLES

CLASSES = ["background", "scream", "cry", "help"]
MODEL = os.path.join(_ROOT, "ml", "out", "stage1_int8.tflite")


def read_wav_16k(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    if sr != SR and len(x) > 1:
        idx = np.linspace(0, len(x) - 1, int(len(x) * SR / sr)).astype(np.int64)
        x = x[idx]
    m = np.max(np.abs(x)) if len(x) else 0.0
    return (x / m).astype(np.float32) if m > 1e-6 else x


class Stage1Int8:
    def __init__(self, model_path=MODEL):
        import tensorflow as tf
        self._it = tf.lite.Interpreter(model_path=model_path)
        self._it.allocate_tensors()
        self._in = self._it.get_input_details()[0]
        self._out = self._it.get_output_details()[0]

    def predict(self, window):
        feat = compute_mfcc(window)[None, ..., None].astype(np.float32)
        s, z = self._in["quantization"]
        q = np.clip(np.round(feat / s + z), -128, 127).astype(np.int8)
        self._it.set_tensor(self._in["index"], q)
        self._it.invoke()
        out = self._it.get_tensor(self._out["index"]).astype(np.float32)
        s, z = self._out["quantization"]
        return (out[0] - z) * s

    def predict_clip(self, x):
        """Max distress over 2 s windows (hop 1 s), like the firmware loop."""
        if len(x) <= N_SAMPLES:
            wins = [np.pad(x, (0, N_SAMPLES - len(x)))]
        else:
            wins = [x[i:i + N_SAMPLES]
                    for i in range(0, len(x) - N_SAMPLES + 1, SR)]
        probs = np.stack([self.predict(w) for w in wins])
        best = int(probs[:, 1:].sum(axis=1).argmax())
        return probs[best]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--dir", help="score every wav in a directory")
    args = ap.parse_args()
    paths = list(args.paths)
    if args.dir:
        paths += sorted(glob.glob(os.path.join(args.dir, "*.wav")))
    if not paths:
        sys.exit("give wav paths or --dir")

    m = Stage1Int8()
    for p in paths:
        probs = m.predict_clip(read_wav_16k(p))
        cls = CLASSES[int(probs.argmax())]
        pretty = "  ".join(f"{c}={q:.2f}" for c, q in zip(CLASSES, probs))
        print(f"{os.path.basename(p):22s} -> {cls:10s} [{pretty}]")


if __name__ == "__main__":
    main()
