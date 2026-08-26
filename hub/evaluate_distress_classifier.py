"""Evaluate a trained distress classifier on a curated WAV dataset.

This is a simple final-year-project evaluation utility. It reports accuracy,
precision, recall, F1, specificity and the confusion matrix. The training
script should be used to create the model first.
"""
from __future__ import annotations

import argparse
import os
import wave

import numpy as np

from .distress_classifier import DistressClassifier, build_feature_vector, CLASS_NAMES
from .yamnet_detector import get_detector

LABEL_DIRS = {"distress": "distress", "normal_human": "normal", "background_noise": "noise"}


def load_wav(path: str):
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported WAV width {width}: {path}")
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    return x.astype(np.float32), int(sr)


def collect(root: str):
    for label, dirname in LABEL_DIRS.items():
        folder = os.path.join(root, dirname)
        for base, _, names in os.walk(folder):
            for name in sorted(names):
                if name.lower().endswith(".wav"):
                    yield os.path.join(base, name), label


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="dataset")
    args = parser.parse_args()

    detector = get_detector()
    if detector is None:
        raise SystemExit("YAMNet is unavailable")
    model = DistressClassifier()
    y_true, y_pred = [], []
    rows = []
    for path, label in collect(args.dataset):
        audio, sr = load_wav(path)
        rep = detector.embedding(audio, sr) or detector.class_score_vector(audio, sr)
        pred = model.predict_features(build_feature_vector(audio, sr, rep))
        y_true.append(label)
        y_pred.append(pred.predicted_class)
        rows.append((path, label, pred.predicted_class, pred.distress_probability))

    if not rows:
        raise SystemExit("No WAV files found")
    from sklearn.metrics import classification_report, confusion_matrix
    print("Confusion matrix [background_noise, normal_human, distress]:")
    print(confusion_matrix(y_true, y_pred, labels=list(CLASS_NAMES)))
    print("\nClassification report:")
    print(classification_report(y_true, y_pred, labels=list(CLASS_NAMES), zero_division=0))

    # Distress-vs-rest specificity and false-positive rate.
    truth = np.asarray([x == "distress" for x in y_true])
    pred = np.asarray([x == "distress" for x in y_pred])
    tn = int(np.sum((~truth) & (~pred)))
    fp = int(np.sum((~truth) & pred))
    fn = int(np.sum(truth & (~pred)))
    tp = int(np.sum(truth & pred))
    specificity = tn / max(1, tn + fp)
    fpr = fp / max(1, fp + tn)
    print(f"\nDistress-vs-rest: TP={tp} TN={tn} FP={fp} FN={fn}")
    print(f"Specificity: {specificity:.3f}")
    print(f"False-positive rate: {fpr:.3f}")

    hard_fp = [r for r in rows if r[1] != "distress" and r[2] == "distress"]
    print(f"\nFalse-positive files: {len(hard_fp)}")
    for path, label, _, p in hard_fp[:50]:
        print(f"  {p:.3f}  {label:16s} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
