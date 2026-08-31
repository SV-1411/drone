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


def _resample_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR or audio.size < 2:
        return audio.astype(np.float32)
    n = max(1, int(round(audio.size * SR / sr)))
    return np.interp(np.linspace(0, audio.size - 1, n), np.arange(audio.size), audio).astype(np.float32)


def _fit_length(audio: np.ndarray, length: int, rng: np.random.Generator) -> np.ndarray:
    if audio.size >= length:
        start = int(rng.integers(0, audio.size - length + 1))
        return audio[start:start + length]
    repeats = int(np.ceil(length / max(1, audio.size)))
    return np.tile(audio, repeats)[:length]


def augment_train_audio(audio: np.ndarray, interferers: list[np.ndarray],
                        rng: np.random.Generator) -> np.ndarray:
    """Condition augmentation for the train split only.

    Interferers intentionally contain both ``background_interference`` and
    ordinary human voices.  Mixing ordinary voices is how the trained model
    sees crowded-room/babble conditions rather than only stationary noise.
    """
    x = np.asarray(audio, dtype=np.float32).copy()
    if not x.size:
        return x
    x *= float(rng.uniform(.35, 1.25))
    if interferers and rng.random() < .80:
        noise = _fit_length(interferers[int(rng.integers(len(interferers)))], x.size, rng)
        signal_rms = float(np.sqrt(np.mean(x * x)) + 1e-8)
        noise_rms = float(np.sqrt(np.mean(noise * noise)) + 1e-8)
        # 0--24 dB includes street noise, nearby chatter and a louder crowd.
        target_snr = float(rng.uniform(0.0, 24.0))
        x += noise * (signal_rms / (noise_rms * 10.0 ** (target_snr / 20.0)))
    if rng.random() < .45:
        # First-order low pass simulates a covered phone/pocket or distance.
        alpha = float(rng.uniform(.025, .20))
        filtered = np.empty_like(x); state = 0.0
        for i, value in enumerate(x):
            state += alpha * (float(value) - state); filtered[i] = state
        x = filtered
    if rng.random() < .35:
        # A short decaying echo gives simple room/reverberation variation.
        delay = int(rng.integers(int(.018 * SR), int(.085 * SR)))
        if delay < x.size:
            x[delay:] += x[:-delay] * float(rng.uniform(.12, .38))
    # Random timing is vital for short screams at browser-window boundaries.
    shift = int(rng.integers(0, min(x.size, SR)))
    if shift:
        x = np.concatenate([np.zeros(shift, dtype=np.float32), x])[:x.size]
    return np.clip(x, -.98, .98).astype(np.float32)


def load_split(samples, split: str, *, interferers: list[np.ndarray] | None = None,
               augmentations: int = 0, seed: int = 42):
    items = [sample for sample in samples if sample.split == split]
    if not items:
        raise ValueError(f"manifest has no {split} samples")
    x, y = [], []
    rng = np.random.default_rng(seed)
    for sample in items:
        audio, sr = read_wav(sample.path)
        audio = _resample_16k(audio, sr)
        x.append(log_mel(audio, SR)); y.append(VOICE_CLASSES.index(sample.label))
        for _ in range(augmentations):
            x.append(log_mel(augment_train_audio(audio, interferers or [], rng), SR))
            y.append(VOICE_CLASSES.index(sample.label))
    return np.asarray(x, dtype=np.float32)[..., None], np.asarray(y, dtype=np.int64)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="reviewed voice_manifest.csv")
    parser.add_argument("--output", default="hub/models/voice_distress.tflite")
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--augmentations", type=int, default=2,
                        help="extra train-only crowd/noise/muffle/reverb variants per clip")
    args = parser.parse_args()
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise SystemExit("Training requires TensorFlow on an offline GPU machine; Render does not install it.") from exc
    samples = read_manifest(args.manifest)
    train_interferers = []
    for sample in samples:
        if sample.split == "train" and sample.label in {"background_interference", "ordinary_voice"}:
            audio, sr = read_wav(sample.path)
            train_interferers.append(_resample_16k(audio, sr))
    x_train, y_train = load_split(samples, "train", interferers=train_interferers,
                                  augmentations=max(0, args.augmentations))
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
        "train_augmentations_per_clip": max(0, args.augmentations),
    }
    output.with_name(output.stem + "_meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"wrote {output} and metadata; run held-out evaluation before enabling VOICE_DISTRESS_MODEL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
