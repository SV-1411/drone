"""Build a bootstrap dataset for the Stage-1 model.

This is a STAND-IN dataset so the training and export pipeline can be validated
today, before real field recordings exist. It must be replaced with real audio
in Phase 1 (see docs/PHASE1_AUDIO_BENCH.md). Do not report accuracy on this
data as if it were real detection performance.

What it produces (16 kHz mono WAV under ml/data/):
  help/        real spoken keywords ("help", "bachao", "madad", "save me",
               "help me") rendered with the Windows SAPI voices at several
               rates and pitches. These are genuine speech.
  scream/      synthesized screams: a harmonic voice source with vibrato,
               formant shaping and added noise, swept in pitch.
  cry/         synthesized wails (slower pitch sweeps, breathier).
  background/  street/traffic/wind/hum/chatter textures and silence. These are
               the negatives the model must NOT fire on.

Usage:
  python ml/make_bootstrap_dataset.py                 # ~120 clips/class
  python ml/make_bootstrap_dataset.py --per-class 200
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import wave

import numpy as np

DATA = os.path.join(os.path.dirname(__file__), "data")
SR = 16000
CLIP_S = 2.0
N = int(SR * CLIP_S)
KEYWORDS = ["help", "help me", "bachao", "madad", "save me", "bachao bachao"]


def _write(path: str, x: np.ndarray) -> None:
    x = np.clip(x, -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def _fit(x: np.ndarray, rng) -> np.ndarray:
    """Pad or crop to N samples, placing a shorter clip at a random offset."""
    if len(x) >= N:
        s = rng.integers(0, len(x) - N + 1)
        return x[s:s + N]
    out = np.zeros(N, dtype=np.float32)
    s = rng.integers(0, N - len(x) + 1)
    out[s:s + len(x)] = x
    return out


# ---------------------------------------------------------------------------
# 1. Real spoken keywords via Windows SAPI (System.Speech)
# ---------------------------------------------------------------------------
def gen_keywords(per_class: int, rng) -> None:
    out_dir = os.path.join(DATA, "help"); os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "_tmp.wav")
    made = 0
    attempts = 0
    voices_ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
    )
    try:
        voices = subprocess.run(["powershell", "-NoProfile", "-Command", voices_ps],
                                capture_output=True, text=True, timeout=30).stdout.split()
    except Exception:
        voices = []
    if not voices:
        print("[bootstrap] no SAPI voices; skipping real keyword synthesis")
        return
    print(f"[bootstrap] SAPI voices: {voices}")
    while made < per_class and attempts < per_class * 4:
        attempts += 1
        word = KEYWORDS[rng.integers(0, len(KEYWORDS))]
        voice = voices[rng.integers(0, len(voices))]
        rate = int(rng.integers(-3, 4))          # SAPI rate -10..10
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"try {{ $s.SelectVoice('{voice}') }} catch {{}};"
            f"$s.Rate = {rate};"
            f"$s.SetOutputToWaveFile('{tmp}');"
            f"$s.Speak('{word}'); $s.Dispose()"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=30)
            # SAPI writes at its own sample rate; resample to 16 kHz mono
            with wave.open(tmp, "rb") as r:
                sr0 = r.getframerate(); ch = r.getnchannels(); sw = r.getsampwidth()
                raw = r.readframes(r.getnframes())
            if sw != 2:
                continue
            a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if ch > 1:
                a = a.reshape(-1, ch).mean(axis=1)
            if sr0 != SR and len(a) > 1:
                idx = np.linspace(0, len(a) - 1, int(len(a) * SR / sr0)).astype(np.int64)
                a = a[idx]
            # random gain + a touch of noise so the model sees variety
            a = a * rng.uniform(0.5, 1.0) + rng.normal(0, 0.004, len(a)).astype(np.float32)
            _write(os.path.join(out_dir, f"kw_{made:04d}.wav"), _fit(a, rng))
            made += 1
        except Exception:
            continue
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f"[bootstrap] help/ (real TTS keywords): {made} clips")


# ---------------------------------------------------------------------------
# 2. Synthesized screams and cries
# ---------------------------------------------------------------------------
def _voice_source(f0: np.ndarray, sr: int, harmonics: int, jitter: float, rng) -> np.ndarray:
    t = np.arange(len(f0)) / sr
    phase = 2 * np.pi * np.cumsum(f0) / sr
    x = np.zeros(len(f0), dtype=np.float32)
    for h in range(1, harmonics + 1):
        amp = 1.0 / h
        x += amp * np.sin(h * phase + rng.normal(0, jitter))
    return x / (np.max(np.abs(x)) + 1e-9)


def gen_screams(per_class: int, rng) -> None:
    out_dir = os.path.join(DATA, "scream"); os.makedirs(out_dir, exist_ok=True)
    for i in range(per_class):
        dur = rng.uniform(0.8, 1.8)
        n = int(dur * SR)
        t = np.arange(n) / SR
        base = rng.uniform(700, 1300)
        sweep = base + rng.uniform(-200, 400) * np.sin(2 * np.pi * rng.uniform(0.5, 2.0) * t)
        vibrato = 1 + 0.03 * np.sin(2 * np.pi * rng.uniform(4, 8) * t)
        f0 = sweep * vibrato
        x = _voice_source(f0, SR, harmonics=rng.integers(6, 14), jitter=0.15, rng=rng)
        # amplitude envelope: fast attack, sustained, decay
        env = np.ones(n)
        a = int(0.05 * n); d = int(0.3 * n)
        env[:a] = np.linspace(0, 1, a)
        env[-d:] = np.linspace(1, 0, d)
        x = x * env
        x = 0.85 * x + 0.15 * rng.normal(0, 0.3, n).astype(np.float32) * env  # breath noise
        _write(os.path.join(out_dir, f"scream_{i:04d}.wav"), _fit(x.astype(np.float32), rng))
    print(f"[bootstrap] scream/: {per_class} clips")


def gen_cries(per_class: int, rng) -> None:
    out_dir = os.path.join(DATA, "cry"); os.makedirs(out_dir, exist_ok=True)
    for i in range(per_class):
        dur = rng.uniform(1.0, 1.8)
        n = int(dur * SR); t = np.arange(n) / SR
        base = rng.uniform(350, 600)
        f0 = base * (1 + 0.4 * np.sin(2 * np.pi * rng.uniform(0.7, 1.6) * t))
        x = _voice_source(f0, SR, harmonics=rng.integers(4, 9), jitter=0.25, rng=rng)
        env = 0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(0.8, 1.5) * t)  # wailing
        x = 0.7 * x * env + 0.3 * rng.normal(0, 0.25, n).astype(np.float32)
        _write(os.path.join(out_dir, f"cry_{i:04d}.wav"), _fit(x.astype(np.float32), rng))
    print(f"[bootstrap] cry/: {per_class} clips")


# ---------------------------------------------------------------------------
# 3. Background negatives (must NOT trigger)
# ---------------------------------------------------------------------------
def gen_background(per_class: int, rng) -> None:
    out_dir = os.path.join(DATA, "background"); os.makedirs(out_dir, exist_ok=True)
    for i in range(per_class):
        kind = i % 6
        if kind == 0:            # near silence with faint hum
            x = 0.002 * rng.normal(0, 1, N) + 0.01 * np.sin(2 * np.pi * 50 * np.arange(N) / SR)
        elif kind == 1:          # traffic rumble (low-pass noise)
            x = rng.normal(0, 0.3, N)
            for _ in range(4):
                x = np.convolve(x, np.ones(20) / 20, mode="same")
        elif kind == 2:          # wind (modulated noise)
            env = 0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(0.2, 0.8) * np.arange(N) / SR)
            x = rng.normal(0, 0.25, N) * env
        elif kind == 3:          # distant chatter (amplitude-modulated bandnoise)
            x = rng.normal(0, 0.2, N)
            x *= (0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(2, 5) * np.arange(N) / SR))
        elif kind == 4:          # car horn / tone bursts (steady, not scream-like)
            x = np.zeros(N)
            f = rng.uniform(400, 500)
            for s in range(0, N, int(0.5 * SR)):
                x[s:s + int(0.25 * SR)] = 0.4 * np.sin(2 * np.pi * f * np.arange(int(0.25 * SR)) / SR)
        else:                    # street music (chords)
            t = np.arange(N) / SR
            x = sum(0.15 * np.sin(2 * np.pi * f * t) for f in rng.uniform(200, 800, 3))
        x = x + 0.01 * rng.normal(0, 1, N)
        _write(os.path.join(out_dir, f"bg_{i:04d}.wav"), x.astype(np.float32))
    print(f"[bootstrap] background/: {per_class} clips")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    os.makedirs(DATA, exist_ok=True)
    print(f"[bootstrap] writing ~{args.per_class} clips/class to {DATA}")
    gen_background(args.per_class, rng)
    gen_screams(args.per_class, rng)
    gen_cries(args.per_class, rng)
    gen_keywords(args.per_class, rng)   # last: real TTS, slowest
    print("[bootstrap] done. NOTE: synthetic + TTS stand-in data — retrain on "
          "real field recordings before deployment (docs/PHASE1_AUDIO_BENCH.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
