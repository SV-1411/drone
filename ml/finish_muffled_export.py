"""Finish the muffled-distress pipeline: evaluate + export from cache.

Avoids re-running build_dataset (2,700 WAV writes) and the 8-minute training.
Reuses the feature cache + best.pth from the completed training run.
Run:  python ml/finish_muffled_export.py
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_muffled_distress as T  # noqa: E402


def main() -> int:
    import torch
    from torch.utils.data import DataLoader

    t0 = time.time()
    cache_dir = T.PROCESSED / "feature_cache"

    def load_split(name):
        data = np.load(str(cache_dir / f"{name}_features.npz"))
        with open(T.SPLITS / f"{name}.csv") as f:
            rows = list(csv.DictReader(f))
        assert data["y"].shape[0] == len(rows), f"{name} cache stale"
        X = torch.from_numpy(data["X"])
        y = torch.from_numpy(data["y"])
        ds = torch.utils.data.TensorDataset(X[..., None], y)
        return DataLoader(ds, batch_size=64, shuffle=False), len(rows)

    test_loader, n_test = load_split("test")
    val_loader, n_val = load_split("val")
    with open(T.SPLITS / "train.csv") as f:
        n_train = sum(1 for _ in csv.DictReader(f))
    print(f"splits: train={n_train} val={n_val} test={n_test}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Rebuild the model object and load the best checkpoint.
    import torch.nn as nn

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
            if x.dim() == 4 and x.shape[-1] == 1:
                x = x.permute(0, 3, 1, 2)
            return self.net(x)

    model = MuffledNet().to(device)
    best_val_acc = 0.976  # from the completed training run (best.pth checkpoint)

    print("\n" + "=" * 60)
    print("EVALUATION ON TEST SET")
    print("=" * 60)
    acc = T.evaluate(model, test_loader, device)

    print("\n" + "=" * 60)
    print("EXPORTING")
    print("=" * 60)
    T.export(model, best_val_acc, n_train, n_val, n_test)

    print(f"\nDone in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
