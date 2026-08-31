"""Train and export the compact Render TFLite voice-distress model.

This command intentionally requires a reviewed manifest.  It does not download
or scrape public-web audio, and it will fail if a speaker/source leaks between
train, validation, and test partitions.
"""
from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path

import numpy as np

from hub.voice_dataset import read_manifest
from hub.voice_decision import SR, VOICE_CLASSES, log_mel


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr, channels, width = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError(f"{path}: only 16-bit WAV is supported by the reproducible trainer")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    return x, sr


def load_split(samples, split: str):
    items = [sample for sample in samples if sample.split == split]
    if not items:
        raise ValueError(f"manifest has no {split} samples")
    x, y = [], []
    for sample in items:
        audio, sr = read_wav(sample.path)
        x.append(log_mel(audio, sr))
        y.append(VOICE_CLASSES.index(sample.label))
    return np.asarray(x, dtype=np.float32)[..., None], np.asarray(y, dtype=np.int64)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="reviewed voice_manifest.csv")
    parser.add_argument("--output", default="hub/models/voice_distress.tflite")
    parser.add_argument("--epochs", type=int, default=35)
    args = parser.parse_args()
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise SystemExit("Training requires TensorFlow on an offline GPU machine; Render does not install it.") from exc
    samples = read_manifest(args.manifest)
    x_train, y_train = load_split(samples, "train")
    x_val, y_val = load_split(samples, "validation")
    model = tf.keras.Sequential([
        tf.keras.layers.Input((96, 64, 1)),
        tf.keras.layers.LayerNormalization(),
        tf.keras.layers.Conv2D(24, 3, padding="same", activation="relu"),
        tf.keras.layers.MaxPool2D(),
        tf.keras.layers.SeparableConv2D(48, 3, padding="same", activation="relu"),
        tf.keras.layers.MaxPool2D(),
        tf.keras.layers.SeparableConv2D(72, 3, padding="same", activation="relu"),
        tf.keras.layers.GlobalAveragePooling2D(),
        tf.keras.layers.Dropout(.25),
        tf.keras.layers.Dense(len(VOICE_CLASSES), activation="softmax"),
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(2e-3),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    weights = np.bincount(y_train, minlength=len(VOICE_CLASSES)).astype(np.float32)
    class_weight = {i: float(weights.sum() / max(1.0, len(weights) * count)) for i, count in enumerate(weights)}
    model.fit(x_train, y_train, validation_data=(x_val, y_val), epochs=args.epochs,
              batch_size=32, class_weight=class_weight,
              callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=6,
                                                           restore_best_weights=True)])
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    output.write_bytes(converter.convert())
    metadata = {
        "version": "voice-distress-v1", "classes": list(VOICE_CLASSES), "sample_rate": SR,
        "input": "log-mel [96,64,1]", "manifest": str(Path(args.manifest).resolve()),
        "train_samples": int(len(y_train)), "validation_samples": int(len(y_val)),
    }
    output.with_name(output.stem + "_meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"wrote {output} and metadata; run held-out evaluation before enabling VOICE_DISTRESS_MODEL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
