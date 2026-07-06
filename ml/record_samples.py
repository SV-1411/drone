"""Record labelled audio clips for the real Phase-1 dataset.

Run this on a laptop (or the Pi) with a microphone to collect the field data
that replaces the bootstrap set. Each clip is saved as 16 kHz mono WAV under
ml/data/<label>/.

    pip install sounddevice
    python ml/record_samples.py --label scream --count 30 --seconds 2
    python ml/record_samples.py --label help --count 50
    python ml/record_samples.py --label background --count 100

Recording protocol (see docs/PHASE1_AUDIO_BENCH.md):
  * scream:     several people, indoor and outdoor, near and far (3 to 20 m)
  * help:       "help", "bachao", "madad" from many speakers, varied volume
  * cry:        distress crying / sobbing
  * background: the exact deployment noise - traffic, crowd, wind, music,
                normal conversation. This class matters most; collect the most.
Aim for at least 200 real clips per class before training for deployment.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import wave

import numpy as np

DATA = os.path.join(os.path.dirname(__file__), "data")
SR = 16000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="scream | help | cry | background")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--gap", type=float, default=0.6, help="pause between clips")
    args = ap.parse_args()
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("pip install sounddevice")

    out_dir = os.path.join(DATA, args.label)
    os.makedirs(out_dir, exist_ok=True)
    existing = len([f for f in os.listdir(out_dir) if f.endswith(".wav")])
    n = int(SR * args.seconds)
    print(f"Recording {args.count} clips of '{args.label}' "
          f"({args.seconds}s each) into {out_dir}")
    print("Press Ctrl+C to stop early.\n")
    made = 0
    try:
        for i in range(args.count):
            for c in (3, 2, 1):
                print(f"  clip {i+1}/{args.count} in {c}...", end="\r", flush=True)
                time.sleep(0.5)
            print(f"  clip {i+1}/{args.count} RECORDING   ", end="\r", flush=True)
            rec = sd.rec(n, samplerate=SR, channels=1, dtype="float32")
            sd.wait()
            x = np.clip(rec[:, 0], -1, 1)
            path = os.path.join(out_dir, f"rec_{existing + made:04d}.wav")
            with wave.open(path, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes((x * 32767).astype(np.int16).tobytes())
            made += 1
            print(f"  clip {i+1}/{args.count} saved -> {os.path.basename(path)}")
            time.sleep(args.gap)
    except KeyboardInterrupt:
        print("\nstopped.")
    print(f"\ndone: {made} clips saved to {out_dir} "
          f"({existing + made} total for '{args.label}')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
