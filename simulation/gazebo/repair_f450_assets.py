#!/usr/bin/env python3
"""Repair generated F450 Gazebo assets after source-model conversion."""
from __future__ import annotations
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

HOME = Path.home()
MODEL_DIRS = [
    HOME / "ardupilot_gazebo" / "models" / "vannikawachh_f450",
    HOME / "ardupilot_gazebo" / "models" / "custom_f450",
]


def repair_sdf(path: Path) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    changed = False

    for parent in root.iter():
        for child in list(parent):
            if child.tag == "script":
                uri = child.find("uri")
                if uri is None or not (uri.text or "").strip():
                    parent.remove(child)
                    changed = True

    for pose in root.iter("pose"):
        vals = (pose.text or "").strip().split()
        if len(vals) == 3 and pose.get("rotation_format") in (None, "euler_rpy"):
            pose.text = " ".join(vals + ["0", "0", "0"])
            changed = True

    if changed:
        tree.write(path, encoding="unicode", xml_declaration=True)
        print(f"Repaired {path}")


for model_dir in MODEL_DIRS:
    if not model_dir.exists():
        continue
    for sdf in model_dir.rglob("*.sdf"):
        repair_sdf(sdf)

print("F450 asset repair complete.")
