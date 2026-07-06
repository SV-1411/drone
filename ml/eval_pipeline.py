"""Evaluate the two-stage acoustic pipeline on a labelled test set.

Reports the numbers the paper's results table needs:
  * Stage-1 per-class recall and the false-trigger rate on background
  * Stage-2 (hub verifier) score separation between distress and background
  * Combined behaviour: of the Stage-1 triggers, how many the hub confirms

Runs the exported int8 tflite (the same weights the ESP32 runs) so the numbers
reflect the deployed model, not the float training model.

    python ml/eval_pipeline.py                      # uses ml/data as the test set
    python ml/eval_pipeline.py --data ml/testset    # a held-out real test set

IMPORTANT: on the bootstrap dataset these numbers validate the pipeline only.
Real detection performance requires the Phase-1 field recordings.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ml.mfcc import mfcc as compute_mfcc, SR
from ml.train_stage1 import CLASSES
OUT = os.path.join(ROOT, "ml", "out")


def load_stage1():
    """Prefer the NumPy-trained MLP (no TensorFlow needed). Fall back to the
    int8 tflite CNN if it was exported with the TF path."""
    from ml import infer_nn
    if infer_nn.available():
        nn = infer_nn.Stage1NN()
        return ("nn", lambda audio: nn.infer(audio)[0])   # -> class index
    try:
        import tensorflow as tf
    except ImportError:
        sys.exit("no model found - run: python ml/train_stage1_numpy.py")
    path = os.path.join(OUT, "stage1_int8.tflite")
    if not os.path.exists(path):
        sys.exit(f"no model found - run: python ml/train_stage1_numpy.py")
    interp = tf.lite.Interpreter(model_path=path); interp.allocate_tensors()
    inp, out = interp.get_input_details()[0], interp.get_output_details()[0]

    def _pred(audio):
        x = compute_mfcc(audio)[None, ..., None]
        s, z = inp["quantization"]
        interp.set_tensor(inp["index"],
                          np.clip(np.round(x / s) + z, -128, 127).astype(inp["dtype"]))
        interp.invoke()
        return int(np.argmax(interp.get_tensor(out["index"])[0]))
    return ("tflite", _pred)


def _read_wav(path):
    import wave
    with wave.open(path, "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "ml", "data"))
    args = ap.parse_args()
    from hub.verifier import Stage2Verifier

    backend_name, predict = load_stage1()
    verifier = Stage2Verifier()

    print(f"classes: {CLASSES}")
    print(f"stage-1 model: {backend_name}   stage-2 backend: "
          f"{type(verifier.backend).name}\n")

    per_class_hit = {c: [0, 0] for c in CLASSES}   # [correct, total]
    s2_scores = {"distress": [], "background": []}
    stage1_triggers = 0
    stage2_confirms = 0

    for ci, cls in enumerate(CLASSES):
        cdir = os.path.join(args.data, cls)
        if not os.path.isdir(cdir):
            continue
        for f in sorted(os.listdir(cdir)):
            if not f.lower().endswith(".wav"):
                continue
            path = os.path.join(cdir, f)
            audio = _read_wav(path)
            pred = predict(audio)
            triggered = pred != 0                    # anything but background
            per_class_hit[cls][1] += 1
            if (cls != "background") == triggered:   # correct trigger decision
                per_class_hit[cls][0] += 1
            # stage-2 on everything stage-1 flags (the real pipeline path)
            if triggered:
                stage1_triggers += 1
                s = verifier.verify_wav(path)
                s2_scores["background" if cls == "background" else "distress"].append(s)
                if s >= 0.50:
                    stage2_confirms += 1

    print(f"STAGE-1 ({backend_name}, the weights the node runs)")
    print(f"  {'class':<12}{'correct-decision rate':>24}")
    for c in CLASSES:
        hit, tot = per_class_hit[c]
        if tot:
            label = "reject rate" if c == "background" else "recall"
            print(f"  {c:<12}{hit/tot:>18.3f}   ({label}, n={tot})")

    def _fmt(xs):
        return f"{sum(xs) / len(xs):.3f}" if xs else "n/a (none reached stage-2)"
    print("\nSTAGE-2 (hub verifier) mean score")
    print(f"  distress clips   {_fmt(s2_scores['distress'])}")
    print(f"  background clips {_fmt(s2_scores['background'])}")
    print(f"\nPIPELINE: {stage1_triggers} stage-1 triggers, "
          f"{stage2_confirms} confirmed by stage-2 (>=0.50)")
    print("\nNOTE: bootstrap data validates the pipeline; real detection rates "
          "need Phase-1 field recordings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
