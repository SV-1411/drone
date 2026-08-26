"""Train the Phase-2 distress SVM from WAV clips.

Dataset layout:
    dataset/distress/*.wav
    dataset/normal/*.wav
    dataset/noise/*.wav

Each WAV file becomes one training example. This avoids leakage that can occur
when adjacent windows from the same recording are randomly split between train
and test sets. The script reports a held-out confusion matrix and classification
metrics before saving the model.
"""
from __future__ import annotations

import argparse
import os
import wave

import numpy as np

from hub.audio_features import FEATURE_NAMES
from hub.distress_classifier import CLASS_NAMES, build_feature_vector, save_artifacts, train_classifier
from hub.yamnet_detector import get_detector

LABEL_DIRS = {"distress": "distress", "normal_human": "normal", "background_noise": "noise"}


def load_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if width == 2:
        x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported WAV sample width {width}: {path}")
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    return x.astype(np.float32), int(sr)


def collect_files(dataset_dir: str):
    rows = []
    for label, dirname in LABEL_DIRS.items():
        root = os.path.join(dataset_dir, dirname)
        if not os.path.isdir(root):
            continue
        for base, _, names in os.walk(root):
            for name in sorted(names):
                if name.lower().endswith(".wav"):
                    rows.append((os.path.join(base, name), label))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="dataset")
    parser.add_argument("--output", default="hub/models")
    args = parser.parse_args()

    try:
        from sklearn.metrics import classification_report, confusion_matrix
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        raise SystemExit("Install scikit-learn before training: pip install -r requirements.txt") from exc

    detector = get_detector()
    if detector is None:
        raise SystemExit("YAMNet is unavailable; cannot build the Phase-2 learned representation.")

    rows = collect_files(args.dataset)
    if len(rows) < 12:
        raise SystemExit("Need at least 12 WAV clips across the dataset classes before training.")
    labels = np.asarray([label for _, label in rows])
    counts = {name: int(np.sum(labels == name)) for name in CLASS_NAMES}
    missing_or_small = [name for name, count in counts.items() if count < 2]
    if missing_or_small:
        raise SystemExit("Each class needs at least 2 clips: " + ", ".join(f"{n}={counts[n]}" for n in CLASS_NAMES))

    X, y = [], []
    representation_dim = None
    for path, label in rows:
        audio, sr = load_wav(path)
        representation = detector.embedding(audio, sr)
        if representation is None:
            representation = detector.class_score_vector(audio, sr)
        representation = np.asarray(representation, dtype=np.float32).reshape(-1)
        representation_dim = representation.size if representation_dim is None else representation_dim
        if representation.size != representation_dim:
            raise SystemExit(f"representation dimension mismatch at {path}")
        X.append(build_feature_vector(audio, sr, representation))
        y.append(label)
        print(f"prepared {label:16s} {path}")

    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    model = train_classifier(X_train, y_train)
    pred = model.predict(X_test)
    print("\nConfusion matrix [background_noise, normal_human, distress]:")
    print(confusion_matrix(y_test, pred, labels=list(CLASS_NAMES)))
    print("\nClassification report:")
    print(classification_report(y_test, pred, labels=list(CLASS_NAMES), zero_division=0))

    save_artifacts(model, {
        "version": 2,
        "classes": CLASS_NAMES,
        "yamnet_representation_dim": int(representation_dim),
        "acoustic_feature_names": tuple(FEATURE_NAMES),
        "feature_order": "[yamnet_representation, phase1_acoustic_features]",
        "classifier": "rbf_svm",
        "threshold": 0.70,
    }, args.output)
    print(f"\nSaved model artifacts to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
