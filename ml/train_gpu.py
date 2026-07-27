"""Real Stage-1 training on a GPU (Colab / Kaggle / Lightning), not synthetic.

Pulls real public audio + your own field recordings, extracts the same MFCC the
firmware uses, trains a CNN with noise-mix augmentation, reports honest metrics
(precision / recall / F1 / confusion matrix / background false-alarm rate), and
exports an int8 TFLite model for the ESP32.

Run on a GPU box (see docs/DATASET_AND_TRAINING.md):
    pip install tensorflow librosa soundfile scikit-learn kaggle
    python ml/train_gpu.py --epochs 60 --kaggle whats2000/human-screaming-detection-dataset

Data sources it combines (whatever is available):
  * ESC-50 (auto-download, no login): environmental sound -> background, and
    crying_baby -> cry.
  * A Kaggle scream dataset (needs ~/.kaggle/kaggle.json) -> scream.
  * Your own recordings under ml/data/<class>/*.wav (ml/record_samples.py).

Outputs to ml/out/: stage1_int8.tflite, stage1_model_data.cc, stage1_metrics.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import urllib.request
import zipfile

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from ml.mfcc import mfcc as compute_mfcc, SR, N_SAMPLES, N_FRAMES, N_MFCC

CLASSES = ["background", "scream", "cry", "help"]
DATA = os.path.join(_ROOT, "ml", "data")
CACHE = os.path.join(_ROOT, "ml", "_cache")
OUT = os.path.join(_ROOT, "ml", "out")


def log(m):
    print(f"[train_gpu] {m}", flush=True)


# --------------------------------------------------------------------------
# data gathering
# --------------------------------------------------------------------------
def _load(path):
    import librosa
    y, _ = librosa.load(path, sr=SR, mono=True)
    return y


def _windows(y):
    """Return one or two 2 s windows from a clip (center, and tail if long)."""
    n = N_SAMPLES
    if len(y) <= n:
        return [np.pad(y, (0, n - len(y)))]
    out = [y[(len(y) - n) // 2: (len(y) - n) // 2 + n]]      # center
    if len(y) >= 2 * n:
        out.append(y[-n:])                                   # tail
    return out


def download_esc50():
    os.makedirs(CACHE, exist_ok=True)
    root = os.path.join(CACHE, "ESC-50-master")
    if os.path.isdir(os.path.join(root, "audio")):
        return root
    zp = os.path.join(CACHE, "esc50.zip")
    log("downloading ESC-50 (~600 MB, once)...")
    urllib.request.urlretrieve(
        "https://github.com/karolpiczak/ESC-50/archive/master.zip", zp)
    with zipfile.ZipFile(zp) as z:
        z.extractall(CACHE)
    os.remove(zp)
    return root


def gather():
    """Return (samples, labels) where samples are raw 16 kHz float arrays."""
    X, y = [], []
    counts = {c: 0 for c in CLASSES}

    # 1) ESC-50 -> background (+ crying_baby -> cry)
    try:
        root = download_esc50()
        import csv
        with open(os.path.join(root, "meta", "esc50.csv")) as f:
            for row in csv.DictReader(f):
                cat = row["category"]
                cls = "cry" if cat == "crying_baby" else "background"
                for w in _windows(_load(os.path.join(root, "audio", row["filename"]))):
                    X.append(w); y.append(CLASSES.index(cls)); counts[cls] += 1
    except Exception as exc:
        log(f"ESC-50 skipped ({exc})")

    # 2) Kaggle scream dataset (optional) -> scream / background by path name
    kg = os.environ.get("_KAGGLE_DIR")
    if kg and os.path.isdir(kg):
        for p in glob.glob(os.path.join(kg, "**", "*.*"), recursive=True):
            if not p.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
                continue
            low = p.lower()
            if "scream" in low and "non" not in low and "not" not in low:
                cls = "scream"
            else:
                cls = "background"
            try:
                for w in _windows(_load(p)):
                    X.append(w); y.append(CLASSES.index(cls)); counts[cls] += 1
            except Exception:
                continue

    # 3) your own recordings under ml/data/<class>/
    for ci, cls in enumerate(CLASSES):
        d = os.path.join(DATA, cls)
        if not os.path.isdir(d):
            continue
        for p in glob.glob(os.path.join(d, "*.wav")):
            try:
                for w in _windows(_load(p)):
                    X.append(w); y.append(ci); counts[cls] += 1
            except Exception:
                continue

    log(f"gathered raw clips per class: {counts}")
    return X, np.array(y, dtype=np.int64), counts


# --------------------------------------------------------------------------
# features + augmentation
# --------------------------------------------------------------------------
def augment(y, rng, noise_pool):
    y = y * rng.uniform(0.6, 1.4)
    y = np.roll(y, rng.integers(0, SR // 2))
    if noise_pool is not None and rng.random() < 0.7:
        n = noise_pool[rng.integers(len(noise_pool))]
        snr = rng.uniform(0, 20)
        ps, pn = np.mean(y ** 2) + 1e-9, np.mean(n ** 2) + 1e-9
        y = y + n * np.sqrt(ps / (pn * 10 ** (snr / 10)))
    return np.clip(y, -1, 1).astype(np.float32)


def featurize(X_raw, y, rng, aug_per_positive=3):
    noise_pool = [X_raw[i] for i in range(len(X_raw)) if y[i] == 0]
    noise_pool = noise_pool[:400] or None
    feats, labels = [], []
    for xi, yi in zip(X_raw, y):
        feats.append(compute_mfcc(xi)); labels.append(yi)
        k = aug_per_positive if yi != 0 else 1
        for _ in range(k):
            feats.append(compute_mfcc(augment(xi, rng, noise_pool))); labels.append(yi)
    X = np.stack(feats)[..., None].astype(np.float32)
    return X, np.array(labels, dtype=np.int64)


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
def build_model(n_classes):
    import tensorflow as tf
    return tf.keras.Sequential([
        tf.keras.layers.Input((N_FRAMES, N_MFCC, 1)),
        tf.keras.layers.Conv2D(16, (5, 3), padding="same", activation="relu"),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.MaxPool2D((2, 1)),
        tf.keras.layers.Conv2D(32, (5, 3), padding="same", activation="relu"),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.MaxPool2D((2, 2)),
        tf.keras.layers.Conv2D(48, (3, 3), padding="same", activation="relu"),
        tf.keras.layers.GlobalAveragePooling2D(),
        tf.keras.layers.Dense(48, activation="relu"),
        tf.keras.layers.Dropout(0.35),
        tf.keras.layers.Dense(n_classes, activation="softmax"),
    ])


def export_tflite(model, X_rep):
    import tensorflow as tf

    def rep():
        for i in np.random.choice(len(X_rep), min(300, len(X_rep)), replace=False):
            yield [X_rep[i:i + 1]]
    c = tf.lite.TFLiteConverter.from_keras_model(model)
    c.optimizations = [tf.lite.Optimize.DEFAULT]
    c.representative_dataset = rep
    c.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    c.inference_input_type = tf.int8; c.inference_output_type = tf.int8
    return c.convert()


def write_c_array(tfl, path):
    lines = ["// Auto-generated by ml/train_gpu.py", "#include <cstdint>",
             "alignas(16) const unsigned char g_stage1_model_data[] = {"]
    for i in range(0, len(tfl), 12):
        lines.append("  " + ", ".join(f"0x{b:02x}" for b in tfl[i:i + 12]) + ",")
    lines += ["};", f"const int g_stage1_model_data_len = {len(tfl)};", ""]
    open(path, "w").write("\n".join(lines))


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--kaggle", help="kaggle dataset slug for scream audio, e.g. user/name")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    try:
        import tensorflow as tf
        from sklearn.metrics import classification_report, confusion_matrix
    except ImportError:
        sys.exit("pip install tensorflow librosa soundfile scikit-learn")
    log(f"GPUs visible: {tf.config.list_physical_devices('GPU')}")
    rng = np.random.default_rng(args.seed)

    if args.kaggle:
        os.makedirs(CACHE, exist_ok=True)
        dest = os.path.join(CACHE, "kaggle_scream")
        if not os.path.isdir(dest):
            log(f"downloading Kaggle dataset {args.kaggle} ...")
            os.system(f'kaggle datasets download -d {args.kaggle} -p "{dest}" --unzip')
        os.environ["_KAGGLE_DIR"] = dest

    X_raw, y_raw, counts = gather()
    present = [i for i in range(len(CLASSES)) if counts[CLASSES[i]] > 0]
    if len(present) < 2 or counts["scream"] == 0:
        log("WARNING: no real scream data found. Provide --kaggle <slug> or record "
            "ml/data/scream/*.wav; training scream on nothing is not meaningful.")

    # speaker/session-disjoint split is ideal; here we split raw clips before
    # augmentation so augmented copies never straddle train/test.
    idx = rng.permutation(len(X_raw))
    n_test = int(0.15 * len(idx)); n_val = int(0.15 * len(idx))
    te, va, trn = idx[:n_test], idx[n_test:n_test + n_val], idx[n_test + n_val:]

    def subset(ids, aug):
        Xr = [X_raw[i] for i in ids]; yr = y_raw[ids]
        return featurize(Xr, yr, rng, aug_per_positive=aug if aug else 0)

    Xtr, ytr = subset(trn, 3)
    Xva, yva = subset(va, 0)
    Xte, yte = subset(te, 0)
    log(f"features: train {Xtr.shape}, val {Xva.shape}, test {Xte.shape}")

    cw = {i: len(ytr) / (len(np.unique(ytr)) * max(1, (ytr == i).sum()))
          for i in np.unique(ytr)}
    model = build_model(len(CLASSES)); model.summary()
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy",
                  metrics=["accuracy"])
    model.fit(Xtr, ytr, validation_data=(Xva, yva), epochs=args.epochs,
              batch_size=args.batch, class_weight=cw,
              callbacks=[tf.keras.callbacks.EarlyStopping(patience=8,
                         restore_best_weights=True)])

    # honest metrics on the held-out test set
    pred = model.predict(Xte).argmax(1)
    rep = classification_report(yte, pred, target_names=CLASSES, output_dict=True,
                                zero_division=0)
    cm = confusion_matrix(yte, pred, labels=list(range(len(CLASSES)))).tolist()
    bg = yte == 0
    false_alarm = float((pred[bg] != 0).mean()) if bg.any() else None
    log("\n" + classification_report(yte, pred, target_names=CLASSES, zero_division=0))
    log(f"background false-alarm rate on test: {false_alarm}")

    os.makedirs(OUT, exist_ok=True)
    tfl = export_tflite(model, Xtr)
    open(os.path.join(OUT, "stage1_int8.tflite"), "wb").write(tfl)
    write_c_array(tfl, os.path.join(OUT, "stage1_model_data.cc"))
    json.dump({"classes": CLASSES, "raw_counts": counts, "report": rep,
               "confusion_matrix": cm, "background_false_alarm_rate": false_alarm,
               "tflite_bytes": len(tfl)},
              open(os.path.join(OUT, "stage1_metrics.json"), "w"), indent=2)
    log(f"exported tflite ({len(tfl)/1024:.1f} KB) + metrics to {OUT}")
    log("commit ml/out/stage1_int8.tflite + stage1_metrics.json; copy the .cc into "
        "firmware/node/ for the -DUSE_TFLM_STAGE1 build. Put the metrics in the paper.")


if __name__ == "__main__":
    main()
