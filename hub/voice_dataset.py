"""Manifest validation for the additive voice-distress training corpus."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .voice_decision import VOICE_CLASSES

REQUIRED_COLUMNS = {
    "path", "split", "label", "speaker_group", "source", "license", "language",
    "environment", "condition", "sha256",
}
ALLOWED_SPLITS = {"train", "validation", "test"}


@dataclass(frozen=True)
class VoiceSample:
    path: Path
    split: str
    label: str
    speaker_group: str
    source: str
    language: str
    condition: str


def read_manifest(path: str | Path) -> list[VoiceSample]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"voice manifest missing columns: {sorted(missing)}")
        rows = list(reader)
    samples: list[VoiceSample] = []
    groups: dict[str, set[str]] = {}
    for index, row in enumerate(rows, 2):
        label, split = row["label"].strip(), row["split"].strip()
        if label not in VOICE_CLASSES:
            raise ValueError(f"row {index}: unsupported label {label!r}")
        if split not in ALLOWED_SPLITS:
            raise ValueError(f"row {index}: unsupported split {split!r}")
        audio = Path(row["path"])
        if not audio.is_absolute():
            audio = path.parent / audio
        if not audio.exists():
            raise ValueError(f"row {index}: missing audio {audio}")
        group = row["speaker_group"].strip() or row["source"].strip()
        groups.setdefault(group, set()).add(split)
        samples.append(VoiceSample(audio, split, label, group, row["source"].strip(),
                                   row["language"].strip(), row["condition"].strip()))
    leaked = sorted(group for group, splits in groups.items() if len(splits) > 1)
    if leaked:
        raise ValueError(f"speaker/source leakage across splits: {leaked[:8]}")
    if not samples:
        raise ValueError("voice manifest contains no samples")
    return samples
