"""Build the local YAMNet test set: convert the real scream to 16 kHz WAV and
synthesize the noise / demo-button clips. Run from repo root:
    .venv\\Scripts\\python.exe ml\\testclips\\make_clips.py
"""
import os

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000


def to16k(x, sr):
    if sr == SR:
        return x
    idx = np.linspace(0, len(x) - 1, int(len(x) * SR / sr)).astype(np.int64)
    return x[idx]


# real scream (Wilhelm, Wikimedia Commons) -> 16 kHz mono wav
x, sr = sf.read(os.path.join(HERE, "wilhelm.ogg"), dtype="float32")
if x.ndim > 1:
    x = x.mean(axis=1)
sf.write(os.path.join(HERE, "scream_real.wav"), to16k(x, sr), SR)

# white noise, loud (a fan / hiss / wind stand-in)
rng = np.random.default_rng(7)
sf.write(os.path.join(HERE, "noise_white.wav"),
         (0.25 * rng.standard_normal(SR * 3)).astype(np.float32), SR)

# burst noise (door slams / claps: loud impulsive transients)
burst = np.zeros(SR * 3, dtype=np.float32)
for at in (0.4, 1.3, 2.2):
    i = int(at * SR)
    n = int(0.06 * SR)
    burst[i:i + n] = (0.9 * rng.standard_normal(n) *
                      np.exp(-np.linspace(0, 8, n))).astype(np.float32)
sf.write(os.path.join(HERE, "noise_bursts.wav"), burst, SR)

# replica of the /node page's SIMULATE DISTRESS synthScream() -- the demo
# button must keep triggering, so it is part of the test set
n = SR * 2
t = np.arange(n) / SR
f0 = 750 + 250 * np.sin(2 * np.pi * 4 * t)
ph = np.cumsum(2 * np.pi * f0 / SR)
s = sum((1.0 / k) * np.sin(k * ph) for k in range(1, 7))
s = s / 2.0 + 0.12 * (rng.random(n) * 2 - 1)
sf.write(os.path.join(HERE, "scream_synth.wav"),
         np.clip(0.9 * s, -1, 1).astype(np.float32), SR)

print("clips written:", [f for f in sorted(os.listdir(HERE))
                         if f.endswith(".wav")])
