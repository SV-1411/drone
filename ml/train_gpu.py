"""Real Stage-1 training (GPU or CPU), streaming + low-RAM.

Pulls real public audio + your own recordings, extracts the same MFCC the
firmware uses, trains a CNN with real-noise-mix augmentation, reports honest
metrics (precision / recall / F1 / confusion matrix / background false-alarm
rate), and exports an int8 TFLite model for the ESP32.

It streams one file at a time (load -> featurize -> free) so it runs in ~1 GB
of RAM on a laptop CPU; no GPU is required. On a GPU box it just goes faster.

    pip install tensorflow librosa soundfile scikit-learn kaggle
    python ml/train_gpu.py --epochs 40 --kaggle whats2000/human-screaming-detection-dataset

Data sources it combines (whatever is available):
  * ESC-50 (auto-download, no login): environmental sound -> background,
    crying_baby -> cry.
  * A Kaggle scream dataset (needs ~/.kaggle/kaggle.json) -> scream.
  * Your own recordings under ml/data/<class>/*.wav (ml/record_samples.py).

Outputs to ml/out/: stage1_int8.tflite, stage1_model_data.cc, stage1_metrics.json
"""
from __future__ import annotations

import argparse
import csv
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
# audio helpers
# --------------------------------------------------------------------------
def _load(path):
    import librosa
    y, _ = librosa.load(path, sr=SR, mono=True)
    m = np.max(np.abs(y)) if len(y) else 0.0
    return (y / m).astype(np.float32) if m > 1e-6 else y.astype(np.float32)


def _windows(y):
    """One or two 2 s windows from a clip (center, and tail if long enough)."""
    n = N_SAMPLES
    if len(y) <= n:
        return [np.pad(y, (0, n - len(y)))]
    s = (len(y) - n) // 2
    out = [y[s:s + n]]
    if len(y) >= 2 * n:
        out.append(y[-n:])
    return out


def download_esc50():
    os.makedirs(CACHE, exist_ok=True)
    root = os.path.join(CACHE, "ESC-50-master")
    if os.path.isdir(os.path.join(root, "audio")):
        return root
    zp = os.path.join(CACHE, "esc50.zip")
    log("downloading ESC-50 (~600 MB, once)...")
    urllib.request.urlretrieve(
        "https://codeload.github.com/karolpiczak/ESC-50/zip/refs/heads/master", zp)
    with zipfile.ZipFile(zp) as z:
        z.extractall(CACHE)
    os.remove(zp)
    return root


# --------------------------------------------------------------------------
# build a FILE INDEX first (no audio loaded), then stream it
# --------------------------------------------------------------------------
def collect_index(kaggle_dir):
    """Return list of (path, class_idx, is_real) without loading any audio."""
    items = []
    try:
        root = download_esc50()
        with open(os.path.join(root, "meta", "esc50.csv")) as f:
            for row in csv.DictReader(f):
                cls = "cry" if row["category"] == "crying_baby" else "background"
                items.append((os.path.join(root, "audio", row["filename"]),
                              CLASSES.index(cls), True))
    except Exception as exc:
        log(f"ESC-50 skipped ({exc})")

    if kaggle_dir and os.path.isdir(kaggle_dir):
        for p in glob.glob(os.path.join(kaggle_dir, "**", "*.*"), recursive=True):
            if not p.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
                continue
            low = p.lower()
            real_scream = "scream" in low and "non" not in low and "not" not in low
            items.append((p, CLASSES.index("scream" if real_scream else "background"), True))

    for ci, cls in enumerate(CLASSES):
        for p in glob.glob(os.path.join(DATA, cls, "*.wav")):
            items.append((p, ci, False))     # local bootstrap = synthetic
    return items


def _augment(y, rng, noise):
    y = y * rng.uniform(0.6, 1.4)
    y = np.roll(y, int(rng.integers(0, SR // 2)))
    if noise is not None and rng.random() < 0.75:
        n = noise[rng.integers(len(noise))]
        snr = rng.uniform(0, 20)
        ps, pn = float(np.mean(y ** 2)) + 1e-9, float(np.mean(n ** 2)) + 1e-9
        y = y + n * np.sqrt(ps / (pn * 10 ** (snr / 10)))
    return np.clip(y, -1, 1).astype(np.float32)


def featurize(files, rng, noise, aug):
    """Stream files -> MFCC feature matrix. Frees each clip after use."""
    X, Y = [], []
    for path, ci, _real in files:
        try:
            wins = _windows(_load(path))
        except Exception:
            continue
        for w in wins:
            X.append(compute_mfcc(w)); Y.append(ci)
            if aug:
                for _ in range(3 if ci != 0 else 0):
                    X.append(compute_mfcc(_augment(w, rng, noise))); Y.append(ci)
    return np.stack(X)[..., None].astype(np.float32), np.array(Y, dtype=np.int64)


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
def build_model(n):
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
        tf.keras.layers.Dense(n, activation="softmax"),
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
    c.inference_input_type = tf.int8
    c.inference_output_type = tf.int8
    return c.convert()


def write_c_array(tfl, path):
    out = ["// Auto-generated by ml/train_gpu.py", "#include <cstdint>",
           "alignas(16) const unsigned char g_stage1_model_data[] = {"]
    for i in range(0, len(tfl), 12):
        out.append("  " + ", ".join(f"0x{b:02x}" for b in tfl[i:i + 12]) + ",")
    out += ["};", f"const int g_stage1_model_data_len = {len(tfl)};", ""]
    open(path, "w").write("\n".join(out))


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--kaggle", help="kaggle scream dataset slug, e.g. user/name")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    # keep TF calm on a small laptop
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    try:
        import tensorflow as tf
        from sklearn.metrics import classification_report, confusion_matrix
    except ImportError:
        sys.exit("pip install tensorflow librosa soundfile scikit-learn")
    tf.config.threading.set_intra_op_parallelism_threads(4)
    log(f"TF {tf.__version__}  GPUs={tf.config.list_physical_devices('GPU')}")
    rng = np.random.default_rng(args.seed)

    if args.kaggle:
        os.makedirs(CACHE, exist_ok=True)
        dest = os.path.join(CACHE, "kaggle_scream")
        if not os.path.isdir(dest):
            log(f"downloading Kaggle dataset {args.kaggle} ...")
            os.system(f'kaggle datasets download -d {args.kaggle} -p "{dest}" --unzip')
        kaggle_dir = dest
    else:
        kaggle_dir = None

    items = collect_index(kaggle_dir)
    per = {c: 0 for c in CLASSES}
    real_scream = 0
    for _p, ci, real in items:
        per[CLASSES[ci]] += 1
        real_scream += int(real and ci == CLASSES.index("scream"))
    log(f"file index per class: {per}  (real scream files: {real_scream})")
    if real_scream == 0:
        log("NOTE: scream/help positives are the synthetic bootstrap only. Real "
            "backgrounds still make this far better at NOT false-alarming, but for a "
            "trustworthy scream detector add --kaggle <slug> or record real clips.")

    # split by FILE (so augmented copies never leak across the split)
    idx = rng.permutation(len(items))
    files = [items[i] for i in idx]
    n = len(files); nt = int(0.15 * n); nv = int(0.15 * n)
    test, val, train = files[:nt], files[nt:nt + nv], files[nt + nv:]

    # small raw noise pool from TRAIN backgrounds for mix augmentation
    noise = []
    for path, ci, _r in train:
        if ci == 0 and len(noise) < 300:
            try:
                noise.append(_windows(_load(path))[0])
            except Exception:
                pass
    noise = noise or None
    log(f"noise pool for augmentation: {0 if noise is None else len(noise)} clips")

    Xtr, ytr = featurize(train, rng, noise, aug=True)
    Xva, yva = featurize(val, rng, None, aug=False)
    Xte, yte = featurize(test, rng, None, aug=False)
    log(f"features -> train {Xtr.shape}  val {Xva.shape}  test {Xte.shape}")

    cw = {int(i): len(ytr) / (len(np.unique(ytr)) * max(1, int((ytr == i).sum())))
          for i in np.unique(ytr)}
    model = build_model(len(CLASSES))
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy",
                  metrics=["accuracy"])
    model.summary(print_fn=log)
    model.fit(Xtr, ytr, validation_data=(Xva, yva), epochs=args.epochs,
              batch_size=args.batch, class_weight=cw, verbose=2,
              callbacks=[tf.keras.callbacks.EarlyStopping(
                  patience=8, restore_best_weights=True)])

    pred = model.predict(Xte, verbose=0).argmax(1)
    txt = classification_report(yte, pred, target_names=CLASSES, zero_division=0)
    rep = classification_report(yte, pred, target_names=CLASSES,
                                output_dict=True, zero_division=0)
    cm = confusion_matrix(yte, pred, labels=list(range(len(CLASSES)))).tolist()
    bg = yte == 0
    fa = float((pred[bg] != 0).mean()) if bg.any() else None
    log("\n" + txt)
    log(f"background false-alarm rate on real test audio: {fa}")

    os.makedirs(OUT, exist_ok=True)
    tfl = export_tflite(model, Xtr)
    open(os.path.join(OUT, "stage1_int8.tflite"), "wb").write(tfl)
    write_c_array(tfl, os.path.join(OUT, "stage1_model_data.cc"))
    json.dump({"classes": CLASSES, "file_counts": per, "real_scream_files": real_scream,
               "report": rep, "confusion_matrix": cm,
               "background_false_alarm_rate": fa, "tflite_bytes": len(tfl)},
              open(os.path.join(OUT, "stage1_metrics.json"), "w"), indent=2)
    log(f"exported int8 tflite ({len(tfl)/1024:.1f} KB) + metrics to {OUT}")


if __name__ == "__main__":
    main()
