"""Muffled Voice Distress Classifier — Full Training Pipeline (local data only).

Uses existing dataset/distress, dataset/normal, dataset/noise, ml/data/* clips.
Generates muffled augmentations from distress sources, trains a compact
binary CNN classifier, evaluates, and exports as PyTorch + ONNX.

Run:  python ml/train_muffled_distress.py
"""
from __future__ import annotations

import csv
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE = Path("ml/muffled_training")
RAW = BASE / "raw"
PROCESSED = BASE / "processed"
GENERATED = BASE / "generated"
SPLITS = BASE / "splits"
MODELS = BASE / "models"

SR = 16000
TARGET_CLIPS = SR * 2  # 2 seconds

for d in [RAW / "distress_source", RAW / "non_distress_source",
          PROCESSED / "muffled_distress", PROCESSED / "non_distress",
          PROCESSED / "final", GENERATED / "muffled_distress",
          SPLITS, MODELS]:
    d.mkdir(parents=True, exist_ok=True)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)


# ---------------------------------------------------------------------------
# Log-mel feature extraction (matches hub/voice_decision.py exactly)
# ---------------------------------------------------------------------------
def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + hz / 700.0)

def _mel_to_hz(mel):
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

def _make_mel_filterbank(n_fft=512, bands=64):
    hz = _mel_to_hz(np.linspace(_hz_to_mel(20.0), _hz_to_mel(SR / 2.0), bands + 2))
    bins = np.clip(np.floor((n_fft + 1) * hz / SR).astype(int), 0, n_fft // 2)
    bank = np.zeros((bands, n_fft // 2 + 1), dtype=np.float32)
    for i in range(bands):
        left, mid, right = bins[i:i + 3]
        if mid > left:
            bank[i, left:mid] = np.linspace(0.0, 1.0, mid - left, endpoint=False)
        if right > mid:
            bank[i, mid:right] = np.linspace(1.0, 0.0, right - mid, endpoint=False)
    return bank

MEL_BANK = _make_mel_filterbank()

def log_mel(audio):
    """Deterministic 96x64 log-mel representation."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if x.size < TARGET_CLIPS:
        x = np.pad(x, (0, TARGET_CLIPS - x.size))
    elif x.size > TARGET_CLIPS:
        x = x[-TARGET_CLIPS:]
    frame, hop, n_fft = 400, 160, 512
    count = 1 + (x.size - frame) // hop
    frames = np.stack([x[i * hop:i * hop + frame] for i in range(count)])
    power = np.abs(np.fft.rfft(frames * np.hanning(frame), n=n_fft, axis=1)) ** 2
    mel = np.log(np.maximum(power @ MEL_BANK.T, 1e-8)).astype(np.float32)
    idx = np.linspace(0, mel.shape[0] - 1, 96)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, mel.shape[0] - 1)
    frac = (idx - lo)[:, None]
    return (mel[lo] * (1.0 - frac) + mel[hi] * frac).astype(np.float32)


# ---------------------------------------------------------------------------
# Audio I/O
# ---------------------------------------------------------------------------
def load_wav(path):
    import librosa
    return librosa.load(str(path), sr=SR, mono=True)

def save_wav(path, audio):
    import soundfile as sf
    sf.write(str(path), audio, SR)


# ---------------------------------------------------------------------------
# Muffled augmentation
# ---------------------------------------------------------------------------
def muffle_audio(audio, severity="medium"):
    """Simulate mouth obstruction: LP filter + gain + formant + breath noise."""
    x = audio.copy().astype(np.float32)
    rng = np.random.default_rng()
    presets = {
        "light":  {"lp": 2000, "gain": -6,  "noise": 0.02, "form": 400},
        "medium": {"lp": 1200, "gain": -10, "noise": 0.05, "form": 350},
        "heavy":  {"lp": 800,  "gain": -15, "noise": 0.08, "form": 300},
        "extreme":{"lp": 500,  "gain": -20, "noise": 0.12, "form": 250},
    }
    p = presets.get(severity, presets["medium"])
    cutoff = p["lp"] + rng.uniform(-200, 200)
    alpha = cutoff / (cutoff + SR / (2 * np.pi))
    filt = np.empty_like(x); s = 0.0
    for i in range(len(x)):
        s += alpha * (x[i] - s); filt[i] = s
    x = filt
    x *= 10 ** ((p["gain"] + rng.uniform(-3, 3)) / 20)
    t = np.arange(len(x)) / SR
    x += np.sin(2 * np.pi * (p["form"] + rng.uniform(-50, 50)) * t) * 0.1 * np.abs(x)
    if p["noise"] > 0:
        br = rng.standard_normal(len(x)).astype(np.float32)
        ba = 1500 / (1500 + SR / (2 * np.pi))
        bf = np.empty_like(br); bs = 0.0
        for i in range(len(br)):
            bs += ba * (br[i] - bs); bf[i] = bs
        x += bf * p["noise"] * rng.uniform(0.5, 1.5)
    if rng.random() < 0.4:
        d = int(rng.uniform(0.005, 0.03) * SR)
        if d < len(x):
            x[d:] += x[:-d] * rng.uniform(0.08, 0.25)
    peak = np.max(np.abs(x))
    if peak > 0: x = x / peak * 0.9
    return np.clip(x, -0.98, 0.98).astype(np.float32)


# ---------------------------------------------------------------------------
# Steps 1-4: Build dataset
# ---------------------------------------------------------------------------
def build_dataset():
    print("\n" + "=" * 60)
    print("BUILDING DATASET")
    print("=" * 60)

    # Collect distress source clips
    distress_sources = []
    for src in sorted(Path("dataset/distress").glob("*.wav")):
        distress_sources.append(("asvp", src))
    for src in sorted(Path("ml/data/cry").glob("*.wav")):
        distress_sources.append(("cry", src))
    for src in sorted(Path("ml/data/scream").glob("*.wav")):
        distress_sources.append(("scream", src))
    print(f"Distress source clips: {len(distress_sources)}")

    # Collect non-distress clips
    non_distress = []
    for src in sorted(Path("dataset/normal").glob("*.wav")):
        non_distress.append(("normal", src))
    for src in sorted(Path("ml/data/help").glob("*.wav")):
        non_distress.append(("help", src))
    for src in sorted(Path("dataset/noise").glob("*.wav")):
        non_distress.append(("noise", src))
    for src in sorted(Path("ml/data/background").glob("*.wav")):
        non_distress.append(("bg", src))
    print(f"Non-distress clips: {len(non_distress)}")

    # Generate muffled distress
    muffled_dir = GENERATED / "muffled_distress"
    muffled_dir.mkdir(parents=True, exist_ok=True)
    severities = ["light", "medium", "heavy", "extreme"]

    print("Generating muffled augmentations...")
    muffled_rows = []
    for idx, (src_type, src_path) in enumerate(distress_sources):
        if idx % 50 == 0:
            print(f"  {idx}/{len(distress_sources)}...")
        try:
            audio, _ = load_wav(src_path)
        except Exception:
            continue

        stem = src_path.stem
        # Original
        dst = muffled_dir / f"{stem}_orig.wav"
        save_wav(dst, audio)
        muffled_rows.append({
            "path": str(dst), "label": "muffled_distress", "class": 1,
            "source": f"{src_type}_{stem}",
        })
        # 4 severity levels
        for sev in severities:
            muffled = muffle_audio(audio, sev)
            dst = muffled_dir / f"{stem}_{sev}.wav"
            save_wav(dst, muffled)
            muffled_rows.append({
                "path": str(dst), "label": "muffled_distress", "class": 1,
                "source": f"{src_type}_{stem}",
            })
    print(f"Muffled distress: {len(muffled_rows)} clips")

    # Non-distress rows
    non_rows = []
    for i, (src_type, src_path) in enumerate(non_distress):
        try:
            audio, _ = load_wav(src_path)
        except Exception:
            continue
        dst = PROCESSED / "non_distress" / f"nd_{i:06d}.wav"
        dst.parent.mkdir(parents=True, exist_ok=True)
        save_wav(dst, audio)
        non_rows.append({
            "path": str(dst), "label": "non_distress", "class": 0,
            "source": src_type,
        })
    print(f"Non-distress: {len(non_rows)} clips")

    # Combine + shuffle
    all_rows = muffled_rows + non_rows
    random.shuffle(all_rows)

    n_d = sum(1 for r in all_rows if r["class"] == 1)
    n_n = sum(1 for r in all_rows if r["class"] == 0)
    print(f"\nTotal: {len(all_rows)} | distress={n_d} | non_distress={n_n}")

    # Split
    n_total = len(all_rows)
    n_train = int(0.7 * n_total)
    n_val = int(0.15 * n_total)
    train_rows = all_rows[:n_train]
    val_rows = all_rows[n_train:n_train + n_val]
    test_rows = all_rows[n_train + n_val:]

    for name, rows in [("train", train_rows), ("val", val_rows), ("test", test_rows)]:
        csv_path = SPLITS / f"{name}.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["path", "label", "class", "source"])
            writer.writeheader()
            writer.writerows(rows)
        nd = sum(1 for r in rows if r["class"] == 1)
        nn = sum(1 for r in rows if r["class"] == 0)
        print(f"  {name:6s}: {len(rows):5d} clips  distress={nd:4d}  non_distress={nn:4d}")

    return len(train_rows), len(val_rows), len(test_rows)


# ---------------------------------------------------------------------------
# Step 5: Train
# ---------------------------------------------------------------------------
def train(n_epochs=35, patience=8):
    print("\n" + "=" * 60)
    print("TRAINING CNN")
    print("=" * 60)

    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Precompute features to avoid disk I/O every epoch
    cache_dir = PROCESSED / "feature_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def _precompute_split(csv_path, split_name, augment=False):
        cache_file = cache_dir / f"{split_name}_features.npz"
        if cache_file.exists():
            data = np.load(str(cache_file))
            return torch.from_numpy(data["X"]), torch.from_numpy(data["y"])
        with open(csv_path) as f:
            rows = list(csv.DictReader(f))
        rng = np.random.default_rng(SEED)
        X, y = [], []
        print(f"  Precomputing {split_name} features ({len(rows)} clips)...")
        for i, row in enumerate(rows):
            if i % 200 == 0 and i > 0:
                print(f"    {i}/{len(rows)}")
            audio, _ = load_wav(row["path"])
            label = int(row["class"])
            if augment:
                audio *= float(rng.uniform(0.6, 1.3))
                if rng.random() < 0.3:
                    shift = int(rng.integers(0, min(len(audio), SR)))
                    audio = np.roll(audio, shift)
            feat = log_mel(audio)
            X.append(feat)
            y.append(label)
        X = np.stack(X)
        y = np.array(y, dtype=np.int64)
        np.savez_compressed(str(cache_file), X=X, y=y)
        return torch.from_numpy(X), torch.from_numpy(y)

    class TensorDS(Dataset):
        def __init__(self, X, y):
            self.X = X
            self.y = y
        def __len__(self):
            return len(self.y)
        def __getitem__(self, idx):
            return self.X[idx][..., None], self.y[idx]

    print("Precomputing features...")
    X_train, y_train = _precompute_split(SPLITS / "train.csv", "train", augment=True)
    X_val, y_val = _precompute_split(SPLITS / "val.csv", "val")
    X_test, y_test = _precompute_split(SPLITS / "test.csv", "test")
    print(f"  train={len(y_train)} val={len(y_val)} test={len(y_test)}")

    train_ds = TensorDS(X_train, y_train)
    val_ds = TensorDS(X_val, y_val)
    test_ds = TensorDS(X_test, y_test)

    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=64, shuffle=False, num_workers=0)

    print(f"Train: {len(train_ds)} | Val: {len(val_ds)} | Test: {len(test_ds)}")

    class MuffledNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.LayerNorm([1, 96, 64]),
                nn.Conv2d(1, 24, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(24, 48, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(48, 72, 3, padding=1), nn.ReLU(),
                nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                nn.Dropout(0.25), nn.Linear(72, 2),
            )
        def forward(self, x):
            # channels-last [B, H, W, 1] -> channels-first [B, 1, H, W]
            if x.dim() == 4 and x.shape[-1] == 1:
                x = x.permute(0, 3, 1, 2)
            return self.net(x)

    model = MuffledNet().to(device)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model params: {total_params:,}")

    n_d = int((y_train == 1).sum())
    n_n = int((y_train == 0).sum())
    weights = torch.tensor([n_d / max(1, n_n), 1.0], dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

    print(f"Class weights: non={weights[0]:.3f}, distress={weights[1]:.3f}")
    print(f"Training up to {n_epochs} epochs...\n")

    best_val_acc = 0.0
    no_improve = 0
    start_all = time.time()

    for epoch in range(1, n_epochs + 1):
        t0 = time.time()
        model.train()
        t_loss = t_corr = t_tot = 0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = criterion(logits, y)
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            t_loss += loss.item() * x.size(0)
            t_corr += (logits.argmax(1) == y).sum().item()
            t_tot += x.size(0)

        model.eval()
        v_loss = v_corr = v_tot = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                logits = model(x)
                loss = criterion(logits, y)
                v_loss += loss.item() * x.size(0)
                v_corr += (logits.argmax(1) == y).sum().item()
                v_tot += x.size(0)

        t_acc = t_corr / t_tot
        v_acc = v_corr / v_tot
        scheduler.step(v_loss / v_tot)
        lr = optimizer.param_groups[0]["lr"]
        dt = time.time() - t0

        mark = ""
        if v_acc > best_val_acc:
            best_val_acc = v_acc
            no_improve = 0
            torch.save(model.state_dict(), str(MODELS / "best.pth"))
            mark = " *"
        else:
            no_improve += 1

        msg = f"  Epoch {epoch:2d}/{n_epochs} | train={t_loss/t_tot:.4f}/{t_acc:.3f} | val={v_loss/v_tot:.4f}/{v_acc:.3f} | lr={lr:.5f} | {dt:.1f}s{mark}"
        print(msg)

        if no_improve >= patience:
            print(f"  Early stop at epoch {epoch}")
            break

    total = time.time() - start_all
    print(f"\nTraining done in {total:.1f}s ({total/60:.1f} min)")
    print(f"Best val acc: {best_val_acc:.3f}")
    return model, test_loader, device, best_val_acc


# ---------------------------------------------------------------------------
# Step 6: Evaluate
# ---------------------------------------------------------------------------
def evaluate(model, test_loader, device):
    print("\n" + "=" * 60)
    print("EVALUATION ON TEST SET")
    print("=" * 60)

    import torch
    import torch.nn.functional as F
    from sklearn.metrics import classification_report, confusion_matrix

    model.load_state_dict(torch.load(str(MODELS / "best.pth")))
    model.eval()

    all_p, all_y, all_pr = [], [], []
    with torch.no_grad():
        for x, y in test_loader:
            x = x.to(device)
            logits = model(x)
            probs = F.softmax(logits, dim=1)
            all_p.extend(logits.argmax(1).cpu().numpy())
            all_y.extend(y.numpy())
            all_pr.extend(probs.cpu().numpy())

    print(classification_report(all_y, all_p, target_names=["non_distress", "muffled_distress"]))
    cm = confusion_matrix(all_y, all_p)
    print("Confusion matrix:")
    print(f"  {'':20s} pred_non  pred_dist")
    print(f"  {'actual_non':20s} {cm[0][0]:8d}  {cm[0][1]:8d}")
    print(f"  {'actual_dist':20s} {cm[1][0]:8d}  {cm[1][1]:8d}")

    dp = np.array([p[1] for p in all_pr])
    tl = np.array(all_y)
    print("\nThreshold analysis:")
    print(f"  {'thresh':>6s}  {'Precision':>9s}  {'Recall':>6s}  {'F1':>6s}")
    for th in [0.3, 0.4, 0.5, 0.6, 0.7]:
        pr = (dp >= th).astype(int)
        tp = ((pr == 1) & (tl == 1)).sum()
        fp = ((pr == 1) & (tl == 0)).sum()
        fn = ((pr == 0) & (tl == 1)).sum()
        p = tp / max(1, tp + fp)
        r = tp / max(1, tp + fn)
        f1 = 2 * p * r / max(1e-8, p + r)
        print(f"  {th:6.1f}  {p:9.3f}  {r:6.3f}  {f1:6.3f}")

    return best_val_acc


# ---------------------------------------------------------------------------
# Step 7: Export
# ---------------------------------------------------------------------------
def export(model, best_val_acc, n_train, n_val, n_test):
    print("\n" + "=" * 60)
    print("EXPORTING")
    print("=" * 60)

    import torch

    model.load_state_dict(torch.load(str(MODELS / "best.pth")))

    # PyTorch
    pth = MODELS / "muffled_distress_final.pth"
    torch.save(model.state_dict(), str(pth))
    print(f"PyTorch:  {pth} ({pth.stat().st_size / 1024:.1f} KB)")

    # ONNX
    model.eval()
    dummy = torch.randn(1, 1, 96, 64)
    onnx = MODELS / "muffled_distress.onnx"
    torch.onnx.export(model, dummy, str(onnx),
                      input_names=["log_mel"], output_names=["probs"],
                      dynamic_axes={"log_mel": {0: "batch"}, "probs": {0: "batch"}})
    print(f"ONNX:     {onnx} ({onnx.stat().st_size / 1024:.1f} KB)")

    # Metadata
    meta = {
        "model": "muffled_distress", "version": "v1",
        "classes": ["non_distress", "muffled_distress"],
        "input": "log_mel [B, 1, 96, 64]", "sample_rate": SR,
        "best_val_acc": round(best_val_acc, 4),
        "train": n_train, "val": n_val, "test": n_test,
    }
    (MODELS / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Metadata: {MODELS / 'meta.json'}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()

    n_train, n_val, n_test = build_dataset()
    model, test_loader, device, best_val_acc = train()
    evaluate(model, test_loader, device)
    export(model, best_val_acc, n_train, n_val, n_test)

    total = time.time() - t0
    print("\n" + "=" * 60)
    print("ALL DONE")
    print("=" * 60)
    print(f"Total time: {total:.1f}s ({total/60:.1f} min)")
    print(f"Best val accuracy: {best_val_acc:.3f}")
    print(f"Models saved to: {MODELS.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
