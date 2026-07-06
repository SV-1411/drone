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


def load_tflite():
    try:
        import tensorflow as tf
    except ImportError:
        sys.exit("tensorflow not installed (needed for the tflite interpreter)")
    path = os.path.join(OUT, "stage1_int8.tflite")
    if not os.path.exists(path):
        sys.exit(f"missing {path} - run: python ml/train_stage1.py")
    interp = tf.lite.Interpreter(model_path=path)
    interp.allocate_tensors()
    return interp


def mfcc_input(audio):
    return compute_mfcc(audio)[None, ..., None]      # (1, frames, n_mfcc, 1)


def run_int8(interp, x):
    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]
    s, z = inp["quantization"]
    xq = np.clip(np.round(x / s) + z, -128, 127).astype(inp["dtype"])
    interp.set_tensor(inp["index"], xq)
    interp.invoke()
    y = interp.get_tensor(out["index"]).astype(np.float32)
    so, zo = out["quantization"]
    return (y - zo) * so


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "ml", "data"))
    args = ap.parse_args()
    try:
        import librosa
    except ImportError:
        sys.exit("librosa not installed")
    from hub.verifier import Stage2Verifier, EnergyHeuristicBackend

    interp = load_tflite()
    verifier = Stage2Verifier()
    stage2_name = type(verifier.backend).name

    print(f"classes: {CLASSES}")
    print(f"stage-2 backend: {stage2_name}\n")

    per_class_hit = {c: [0, 0] for c in CLASSES}   # [triggered, total]
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
            audio, _ = librosa.load(path, sr=SR, mono=True)
            probs = run_int8(interp, mfcc_input(audio))[0]
            pred = int(np.argmax(probs))
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

    print("STAGE-1 (int8 tflite, deployed weights)")
    print(f"  {'class':<12}{'correct-decision rate':>24}")
    for c in CLASSES:
        hit, tot = per_class_hit[c]
        if tot:
            label = "reject rate" if c == "background" else "recall"
            print(f"  {c:<12}{hit/tot:>18.3f}   ({label}, n={tot})")

    def _mean(xs):
        return sum(xs) / len(xs) if xs else float("nan")
    print("\nSTAGE-2 (hub verifier) mean score")
    print(f"  distress clips   {_mean(s2_scores['distress']):.3f}")
    print(f"  background clips {_mean(s2_scores['background']):.3f}")
    print(f"\nPIPELINE: {stage1_triggers} stage-1 triggers, "
          f"{stage2_confirms} confirmed by stage-2 (>=0.50)")
    print("\nNOTE: bootstrap data validates the pipeline; real detection rates "
          "need Phase-1 field recordings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
