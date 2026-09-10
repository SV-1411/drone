"""Sanity check: run the trained muffled-distress model on real clips.

Answers: does a real scream actually score as distress? What are the
probabilities at the operating thresholds?
Run:  python ml/verify_muffled_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_muffled_distress as T  # noqa: E402


def load_model():
    import torch
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

    m = MuffledNet()
    m.load_state_dict(torch.load(str(T.MODELS / "best.pth"), map_location="cpu"))
    m.eval()
    return m, torch


def predict(model, torch, audio):
    feat = T.log_mel(audio)
    with torch.no_grad():
        logits = model(torch.from_numpy(feat[None, :, :, None]))
        return float(torch.softmax(logits, dim=1)[0, 1])


def main() -> int:
    model, torch = load_model()

    # 1) Original (unmuffled) distress sources — the "my scream is missed" case
    print("=" * 62)
    print("REAL DISTRESS CLIPS (original, unmuffled)")
    print("=" * 62)
    hits = misses = 0
    samples = []
    for src in sorted(Path("dataset/distress").glob("*.wav"))[:40]:
        samples.append(src)
    for src in sorted(Path("ml/data/scream").glob("*.wav"))[:20]:
        samples.append(src)
    for src in sorted(Path("ml/data/cry").glob("*.wav"))[:20]:
        samples.append(src)
    for src in samples:
        try:
            audio, _ = T.load_wav(src)
        except Exception:
            continue
        p = predict(model, torch, audio)
        ok = p >= 0.5
        hits += ok
        misses += not ok
        flag = "OK " if ok else "MISS"
        print(f"  [{flag}] p={p:.3f}  {src.name}")
    print(f"  -> distress recall @0.5: {hits}/{hits + misses}")

    # 2) Voice-evaluation clips (the ones the baseline previously missed)
    print("\n" + "=" * 62)
    print("VOICE-EVALUATION CLIPS (dataset/voice-evaluation)")
    print("=" * 62)
    for src in sorted(Path("dataset/voice-evaluation/audio").glob("*.wav")):
        try:
            audio, _ = T.load_wav(src)
        except Exception:
            continue
        p = predict(model, torch, audio)
        print(f"  p={p:.3f}  {src.name}")

    # 3) Non-distress — false-alarm check
    print("\n" + "=" * 62)
    print("NON-DISTRESS CLIPS")
    print("=" * 62)
    fp = tot = 0
    samples = sorted(Path("dataset/normal").glob("*.wav"))[:20]
    samples += sorted(Path("dataset/noise").glob("*.wav"))[:10]
    samples += sorted(Path("ml/data/background").glob("*.wav"))[:10]
    samples += sorted(Path("ml/data/help").glob("*.wav"))[:10]
    for src in samples:
        try:
            audio, _ = T.load_wav(src)
        except Exception:
            continue
        p = predict(model, torch, audio)
        fp += p >= 0.5
        tot += 1
        flag = "FP " if p >= 0.5 else "ok "
        print(f"  [{flag}] p={p:.3f}  {src.name}")
    print(f"  -> false alarms: {fp}/{tot} @0.5")

    # 4) Muffled distress variants — does it survive muffling?
    print("\n" + "=" * 62)
    print("MUFFLED DISTRESS VARIANTS (generated)")
    print("=" * 62)
    gen = sorted(Path("ml/muffled_training/generated/muffled_distress").glob("*_extreme.wav"))[:10]
    for src in gen:
        audio, _ = T.load_wav(src)
        p = predict(model, torch, audio)
        flag = "OK " if p >= 0.5 else "MISS"
        print(f"  [{flag}] p={p:.3f}  {src.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
