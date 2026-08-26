"""Prepare the complete local training corpus without committing datasets.

Sources:
  * CREMA-D mirror (normal/emotional human hard negatives)
  * ASVP-ESD (fear/scream/panic, crying and pain vocalizations)
  * ESC-50 (environmental/noise hard negatives)

The script downloads/clones data locally, curates a small balanced subset,
and writes dataset/manifest.csv. Raw datasets remain outside the Git tree's
tracked files; only curated WAVs under dataset/{distress,normal,noise} are used
by the training script.

Usage:
    python -m hub.prepare_full_dataset

Optional controls:
    --work-dir .cache/audio-datasets
    --dataset-dir dataset
    --max-per-class 400
    --seed 42

The curation is intentionally conservative. ASVP-ESD's filename encoding is
used to select non-speech fear/scream/panic (emotion 06, subtype 16/36),
sadness/cry (04/14/34/44), and pain/groan (11). CREMA-D is never promoted to
distress merely because it is fearful; it is used as human hard-negative data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import random
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

CREMA_URL = "https://gitlab.com/cs-cooper-lab/crema-d-mirror.git"
ESC50_URL = "https://github.com/karolpiczak/ESC-50.git"
ASVP_URL = "https://zenodo.org/records/4782712/files/ASVP_ESD.zip?download=1"

# ESC-50 classes deliberately selected as environmental negatives. More can be
# added later without changing the model interface.
ESC_NOISE_CLASSES = {
    "siren", "car_horn", "dog", "engine", "helicopter", "train", "airplane",
    "crowd", "rain", "wind", "crackling_fire", "chainsaw", "street_music",
    "drilling", "jackhammer", "washing_machine", "vacuum_cleaner", "clock_alarm",
    "church_bells", "fireworks", "clapping", "footsteps", "water_drops",
}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def ensure_git_repo(url: str, target: Path) -> None:
    if (target / ".git").exists():
        run(["git", "-C", str(target), "pull", "--ff-only"])
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--depth", "1", url, str(target)])


def ensure_asvp(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    archive = target.parent / "ASVP_ESD.zip"
    if not archive.exists():
        print(f"Downloading ASVP-ESD (~1.3 GB) to {archive}")
        urllib.request.urlretrieve(ASVP_URL, archive)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
    return target


def wavs(root: Path):
    yield from root.rglob("*.wav")


def asvp_kind(path: Path) -> str | None:
    """Return distress subtype from ASVP filename encoding when available."""
    parts = path.stem.split("-")
    if len(parts) < 10:
        return None
    # audio-only/non-speech uses vocal channel 02. Emotion is field 3.
    if parts[0] != "03" or parts[1] != "02":
        return None
    emotion = parts[2]
    if emotion == "06" and parts[-1].endswith(("16", "36")):
        return "distress"
    if emotion == "04" and parts[-1].endswith(("14", "34", "44")):
        return "distress"
    if emotion == "11":
        return "distress"
    return None


def cremad_group(path: Path) -> str:
    # CREMA-D filenames begin with the actor id, e.g. 1001_DFA_ANG_XX.wav.
    return path.stem.split("_")[0]


def asvp_group(path: Path) -> str:
    parts = path.stem.split("-")
    return parts[5] if len(parts) >= 6 else path.parent.name


def esc_group(path: Path) -> str:
    # ESC-50 metadata uses fold 1..5. Keep a stable source/fold grouping.
    return path.parent.name


def copy_subset(items, destination: Path, max_count: int, rng: random.Random):
    destination.mkdir(parents=True, exist_ok=True)
    if len(items) > max_count:
        items = rng.sample(items, max_count)
    copied = []
    for src, group, source_label in items:
        digest = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:12]
        dst = destination / f"{source_label}_{digest}.wav"
        if not dst.exists():
            shutil.copy2(src, dst)
        copied.append((str(dst), group, source_label))
    return copied


def write_manifest(rows, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "label", "group", "source"])
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default=".cache/audio-datasets")
    ap.add_argument("--dataset-dir", default="dataset")
    ap.add_argument("--max-per-class", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    work = Path(args.work_dir).resolve()
    dataset = Path(args.dataset_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)

    crema = work / "crema-d-mirror"
    esc = work / "ESC-50"
    asvp = work / "ASVP_ESD"
    ensure_git_repo(CREMA_URL, crema)
    ensure_git_repo(ESC50_URL, esc)
    ensure_asvp(asvp)

    # Never delete an existing dataset automatically. We only write/update the
    # three curated directories when explicitly requested by this preparation.
    for label in ("distress", "normal", "noise"):
        (dataset / label).mkdir(parents=True, exist_ok=True)

    distress = []
    for p in wavs(asvp):
        if asvp_kind(p) == "distress":
            distress.append((p, asvp_group(p), "asvp"))

    normal = []
    for p in wavs(crema):
        normal.append((p, cremad_group(p), "cremad"))

    noise = []
    metadata = esc / "meta" / "esc50.csv"
    if metadata.exists():
        import csv as _csv
        with metadata.open("r", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                if row["category"] in ESC_NOISE_CLASSES:
                    p = esc / "audio" / f"fold{row['fold']}" / row["filename"]
                    if p.exists():
                        noise.append((p, f"esc_fold_{row['fold']}", "esc50"))

    if not distress or not normal or not noise:
        raise SystemExit(
            f"Curation failed: distress={len(distress)}, normal={len(normal)}, noise={len(noise)}. "
            "Check dataset downloads/structures."
        )

    rows = []
    rows.extend((p, "distress", g, s) for p, g, s in copy_subset(distress, dataset / "distress", args.max_per_class, rng))
    rows.extend((p, "normal_human", g, s) for p, g, s in copy_subset(normal, dataset / "normal", args.max_per_class, rng))
    rows.extend((p, "background_noise", g, s) for p, g, s in copy_subset(noise, dataset / "noise", args.max_per_class, rng))
    write_manifest(rows, dataset / "manifest.csv")

    counts = {label: sum(r[1] == label for r in rows) for label in ("distress", "normal_human", "background_noise")}
    print("\nPrepared dataset:")
    for k, v in counts.items():
        print(f"  {k:16s}: {v}")
    print(f"Manifest: {dataset / 'manifest.csv'}")
    print("\nNo raw dataset is committed by this script. The curated WAVs are local training inputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
