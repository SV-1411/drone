from __future__ import annotations

import csv
import wave

import numpy as np
import pytest

from hub.voice_dataset import read_manifest


HEADERS = ["path", "split", "label", "speaker_group", "source", "license",
           "language", "environment", "condition", "sha256"]


def _wav(path):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
        out.writeframes(np.zeros(1600, dtype="<i2").tobytes())


def _manifest(path, rows):
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=HEADERS)
        writer.writeheader(); writer.writerows(rows)


def _row(audio, split, group, label="distressed_speech"):
    return {"path": audio.name, "split": split, "label": label,
            "speaker_group": group, "source": "consented-field", "license": "consent-v1",
            "language": "hi-en", "environment": "outdoor", "condition": "muffled",
            "sha256": "placeholder"}


def test_voice_manifest_accepts_disjoint_speaker_groups(tmp_path):
    train, valid, test = (tmp_path / name for name in ("train.wav", "valid.wav", "test.wav"))
    for path in (train, valid, test): _wav(path)
    manifest = tmp_path / "voice_manifest.csv"
    _manifest(manifest, [_row(train, "train", "s01"), _row(valid, "validation", "s02"),
                         _row(test, "test", "s03", "scream")])
    assert [sample.split for sample in read_manifest(manifest)] == ["train", "validation", "test"]


def test_voice_manifest_rejects_speaker_leakage(tmp_path):
    train, test = tmp_path / "train.wav", tmp_path / "test.wav"
    _wav(train); _wav(test)
    manifest = tmp_path / "voice_manifest.csv"
    _manifest(manifest, [_row(train, "train", "s01"), _row(test, "test", "s01")])
    with pytest.raises(ValueError, match="leakage"):
        read_manifest(manifest)
