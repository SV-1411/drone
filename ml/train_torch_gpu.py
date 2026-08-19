"""Stage-1 training on an NVIDIA GPU via PyTorch (Windows-native).

TensorFlow dropped native-Windows GPU support after 2.10, so on a Windows
box with a CUDA GPU the honest way to train on the GPU is: train the SAME
architecture in PyTorch/CUDA, then port the learned weights into the Keras
model and reuse `train_gpu.py`'s int8 TFLite export for the ESP32. A parity
check verifies the ported Keras model reproduces the torch model's outputs
before anything is exported.

Data / features / split / augmentation / metrics are all reused from
ml/train_gpu.py so the two trainers stay interchangeable:

    pip install torch --index-url https://download.pytorch.org/whl/cu126
    python ml/train_torch_gpu.py --epochs 60

Outputs to ml/out/: stage1_int8.tflite, stage1_model_data.cc, stage1_metrics.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from ml.mfcc import N_FRAMES, N_MFCC
from ml.train_gpu import (CLASSES, OUT, CACHE, _load, _windows, build_model,
                          collect_index, export_tflite, featurize, log,
                          write_c_array)


# --------------------------------------------------------------------------
# torch mirror of ml/train_gpu.py:build_model — layer order matters for the
# weight port: Keras Conv2D(activation="relu") applies relu BEFORE the
# following BatchNormalization layer, so the torch order is conv→relu→BN.
# Keras BN defaults are eps=1e-3, momentum=0.99 (torch momentum = 1-0.99).
# --------------------------------------------------------------------------
def build_torch_model(n):
    import torch.nn as nn

    class Stage1(nn.Module):
        def __init__(self):
            super().__init__()
            self.c1 = nn.Conv2d(1, 16, (5, 3), padding=(2, 1))
            self.b1 = nn.BatchNorm2d(16, eps=1e-3, momentum=0.01)
            self.c2 = nn.Conv2d(16, 32, (5, 3), padding=(2, 1))
            self.b2 = nn.BatchNorm2d(32, eps=1e-3, momentum=0.01)
            self.c3 = nn.Conv2d(32, 48, (3, 3), padding=(1, 1))
            self.fc1 = nn.Linear(48, 48)
            self.drop = nn.Dropout(0.35)
            self.fc2 = nn.Linear(48, n)
            self.relu = nn.ReLU()
            self.p1 = nn.MaxPool2d((2, 1))
            self.p2 = nn.MaxPool2d((2, 2))

        def forward(self, x):                     # x: [B, 1, N_FRAMES, N_MFCC]
            x = self.p1(self.b1(self.relu(self.c1(x))))
            x = self.p2(self.b2(self.relu(self.c2(x))))
            x = self.relu(self.c3(x))
            x = x.mean(dim=(2, 3))                # GlobalAveragePooling2D
            x = self.drop(self.relu(self.fc1(x)))
            return self.fc2(x)                    # logits (softmax in loss)

    return Stage1()


def port_weights_to_keras(tm, km):
    """Copy trained torch weights into the Keras model built by build_model."""
    import torch
    sd = {k: v.detach().cpu().numpy() for k, v in tm.state_dict().items()}

    def conv(name):     # torch [O,I,H,W] -> keras [H,W,I,O]
        return [sd[f"{name}.weight"].transpose(2, 3, 1, 0), sd[f"{name}.bias"]]

    def bn(name):       # keras [gamma, beta, moving_mean, moving_var]
        return [sd[f"{name}.weight"], sd[f"{name}.bias"],
                sd[f"{name}.running_mean"], sd[f"{name}.running_var"]]

    def dense(name):    # torch [out,in] -> keras [in,out]
        return [sd[f"{name}.weight"].T, sd[f"{name}.bias"]]

    weights = (conv("c1") + bn("b1") + conv("c2") + bn("b2") + conv("c3")
               + dense("fc1") + dense("fc2"))
    km.set_weights(weights)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--kaggle-dir", help="dir of a real scream dataset (any layout)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument("--trials", type=int, default=1,
                    help="train N differently-seeded models, keep best val loss")
    ap.add_argument("--cache-features", action="store_true",
                    help="reuse ml/_cache/feats.npz if present (features are "
                         "deterministic for a fixed --seed)")
    args = ap.parse_args()

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    import torch
    import torch.nn as nn
    from sklearn.metrics import classification_report, confusion_matrix

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dev_name = torch.cuda.get_device_name(0) if dev.type == "cuda" else "CPU"
    log(f"torch {torch.__version__}  device: {dev_name}")
    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)

    feats_cache = os.path.join(CACHE, f"feats_seed{args.seed}.npz")
    if args.cache_features and os.path.exists(feats_cache):
        z = np.load(feats_cache, allow_pickle=True)
        Xtr, ytr, Xva, yva, Xte, yte = (z[k] for k in
                                        ("Xtr", "ytr", "Xva", "yva", "Xte", "yte"))
        per = z["per"].item(); real_scream = int(z["real_scream"])
        log(f"loaded cached features {feats_cache}")
        log(f"file index per class: {per}  (real scream files: {real_scream})")
    else:
        kaggle_dir = args.kaggle_dir or os.path.join(CACHE, "kaggle_scream")
        items = collect_index(kaggle_dir if os.path.isdir(kaggle_dir) else None)
        per = {c: 0 for c in CLASSES}
        real_scream = 0
        for _p, ci, real in items:
            per[CLASSES[ci]] += 1
            real_scream += int(real and ci == CLASSES.index("scream"))
        log(f"file index per class: {per}  (real scream files: {real_scream})")

        # split by FILE (augmented copies never leak across the split)
        idx = rng.permutation(len(items))
        files = [items[i] for i in idx]
        n = len(files); nt = int(0.15 * n); nv = int(0.15 * n)
        test, val, train = files[:nt], files[nt:nt + nv], files[nt + nv:]

        noise = []
        for path, ci, _r in train:
            if ci == 0 and len(noise) < 300:
                try:
                    noise.append(_windows(_load(path))[0])
                except Exception:
                    pass
        noise = noise or None
        log(f"noise pool for augmentation: "
            f"{0 if noise is None else len(noise)} clips")

        Xtr, ytr = featurize(train, rng, noise, aug=True)
        Xva, yva = featurize(val, rng, None, aug=False)
        Xte, yte = featurize(test, rng, None, aug=False)
        if args.cache_features:
            np.savez_compressed(feats_cache, Xtr=Xtr, ytr=ytr, Xva=Xva,
                                yva=yva, Xte=Xte, yte=yte, per=per,
                                real_scream=real_scream)
            log(f"cached features -> {feats_cache}")
    log(f"features -> train {Xtr.shape}  val {Xva.shape}  test {Xte.shape}")

    # per-class weights, same formula as train_gpu.py
    w = np.ones(len(CLASSES), dtype=np.float32)
    for i in np.unique(ytr):
        w[i] = len(ytr) / (len(np.unique(ytr)) * max(1, int((ytr == i).sum())))

    def loader(X, y, shuffle):
        ds = torch.utils.data.TensorDataset(
            torch.from_numpy(X.transpose(0, 3, 1, 2)),   # NHWC -> NCHW
            torch.from_numpy(y))
        return torch.utils.data.DataLoader(ds, batch_size=args.batch,
                                           shuffle=shuffle)

    tr, va = loader(Xtr, ytr, True), loader(Xva, yva, False)
    lossf = nn.CrossEntropyLoss(weight=torch.from_numpy(w).to(dev))

    def train_one(seed):
        torch.manual_seed(seed)
        model = build_torch_model(len(CLASSES)).to(dev)
        opt = torch.optim.Adam(model.parameters(), lr=1e-3)
        best_loss, best_state, best_ep, bad = float("inf"), None, 0, 0
        for ep in range(1, args.epochs + 1):
            model.train()
            tl = correct = seen = 0
            for xb, yb in tr:
                xb, yb = xb.to(dev), yb.to(dev)
                opt.zero_grad()
                out = model(xb)
                loss = lossf(out, yb)
                loss.backward(); opt.step()
                tl += float(loss.detach()) * len(yb)
                correct += int((out.argmax(1) == yb).sum()); seen += len(yb)
            model.eval()
            vl = vc = vn = 0
            with torch.no_grad():
                for xb, yb in va:
                    xb, yb = xb.to(dev), yb.to(dev)
                    out = model(xb)
                    vl += float(lossf(out, yb)) * len(yb)
                    vc += int((out.argmax(1) == yb).sum()); vn += len(yb)
            log(f"seed {seed}  epoch {ep:3d}  loss {tl/seen:.4f} "
                f"acc {correct/seen:.3f}   val_loss {vl/vn:.4f} val_acc {vc/vn:.3f}")
            if vl / vn < best_loss - 1e-5:
                best_loss, best_ep, bad = vl / vn, ep, 0
                best_state = {k: v.detach().cpu().clone()
                              for k, v in model.state_dict().items()}
            else:
                bad += 1
                if bad >= args.patience:
                    log(f"seed {seed}: early stop (best epoch {best_ep}, "
                        f"val_loss {best_loss:.4f})")
                    break
        return best_loss, best_state, best_ep

    results = [train_one(args.seed + t) for t in range(args.trials)]
    best_loss, best_state, best_ep = min(results, key=lambda r: r[0])
    log(f"best of {args.trials} trials: val_loss {best_loss:.4f} "
        f"(epoch {best_ep})")
    model = build_torch_model(len(CLASSES)).to(dev)
    model.load_state_dict(best_state)
    model.eval()

    # ---- port to Keras and VERIFY parity before exporting ------------------
    kmodel = build_model(len(CLASSES))
    port_weights_to_keras(model, kmodel)
    with torch.no_grad():
        tp = torch.softmax(model(torch.from_numpy(
            Xte.transpose(0, 3, 1, 2)).to(dev)), dim=1).cpu().numpy()
    kp = kmodel.predict(Xte, verbose=0)
    parity = float(np.abs(tp - kp).max())
    agree = float((tp.argmax(1) == kp.argmax(1)).mean())
    log(f"torch->keras parity: max |dprob| {parity:.2e}, argmax agreement {agree:.4f}")
    # float32 backend differences (cuDNN vs oneDNN) legitimately reach ~2e-3
    # in softmax probs; a real port bug is orders of magnitude larger and
    # breaks argmax agreement immediately.
    if parity > 5e-3 or agree < 1.0:
        sys.exit("weight port mismatch - refusing to export")

    # ---- metrics from the Keras model (the artifact that ships) ------------
    pred = kp.argmax(1)
    txt = classification_report(yte, pred, target_names=CLASSES, zero_division=0)
    rep = classification_report(yte, pred, target_names=CLASSES,
                                output_dict=True, zero_division=0)
    cm = confusion_matrix(yte, pred, labels=list(range(len(CLASSES)))).tolist()
    bg = yte == 0
    fa = float((pred[bg] != 0).mean()) if bg.any() else None
    log("\n" + txt)
    log(f"background false-alarm rate on real test audio: {fa}")

    os.makedirs(OUT, exist_ok=True)
    tfl = export_tflite(kmodel, Xtr)
    open(os.path.join(OUT, "stage1_int8.tflite"), "wb").write(tfl)
    write_c_array(tfl, os.path.join(OUT, "stage1_model_data.cc"))
    json.dump({"classes": CLASSES, "file_counts": per,
               "real_scream_files": real_scream,
               "trained_on": dev_name, "best_epoch": best_ep,
               "torch_keras_parity_max_abs": parity,
               "report": rep, "confusion_matrix": cm,
               "background_false_alarm_rate": fa, "tflite_bytes": len(tfl)},
              open(os.path.join(OUT, "stage1_metrics.json"), "w"), indent=2)
    log(f"exported int8 tflite ({len(tfl)/1024:.1f} KB) + metrics to {OUT}")


if __name__ == "__main__":
    main()
