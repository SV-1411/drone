"""Run the complete Stage-2 verifier on one WAV file without hardware.

Example:
    python -m hub.verify_clip path/to/scream.wav
"""
from __future__ import annotations

import argparse
import json

from .verifier import Stage2Verifier


def main() -> int:
    parser = argparse.ArgumentParser(description="Drone distress verification demo")
    parser.add_argument("wav", help="WAV file to verify")
    parser.add_argument("--threshold", type=float, default=0.70)
    parser.add_argument("--min-frames", type=int, default=3)
    args = parser.parse_args()

    verifier = Stage2Verifier(threshold=args.threshold, min_positive_frames=args.min_frames)
    result = verifier.verify_wav_detail(args.wav)
    payload = {
        "distress_confirmed": result.distress_confirmed,
        "classifier_probability": result.classifier_probability,
        "yamnet_distress_probability": result.yamnet_distress_probability,
        "temporal_positive_frames": result.temporal_positive_frames,
        "temporal_frames": result.temporal_frames,
        "temporal_gate_passed": result.temporal_gate_passed,
        "acoustic_severity": result.acoustic_severity,
        "roughness": result.roughness,
        "rms_intensity": result.rms_intensity,
        "spectral_score": result.spectral_score,
        "backend": result.backend,
        "reason": result.reason,
    }
    print(json.dumps(payload, indent=2))
    return 0 if result.distress_confirmed else 1


if __name__ == "__main__":
    raise SystemExit(main())
