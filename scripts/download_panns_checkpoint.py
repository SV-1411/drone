"""Download and verify the PANNs CNN14 checkpoint during a cloud build.

The model is intentionally not committed: GitHub rejects files of this size
and the binary should not be duplicated in the source repository.  Render runs
this script after installing the CPU-only PANN runtime.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.request import Request, urlopen


URL = (
    "https://huggingface.co/thelou1s/panns-inference/resolve/main/"
    "Cnn14_mAP%3D0.431.pth"
)
SHA256 = "0dc499e40e9761ef5ea061ffc77697697f277f6a960894903df3ada000e34b31"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / ".panns" / "Cnn14_mAP=0.431.pth"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> None:
    destination = Path(os.environ.get("PANN_CHECKPOINT_PATH", DEFAULT_PATH))
    if destination.exists() and digest(destination) == SHA256:
        print(f"PANN checkpoint already verified: {destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    if temporary.exists():
        temporary.unlink()

    print(f"Downloading PANN CNN14 checkpoint to {destination}")
    request = Request(URL, headers={"User-Agent": "VanniKawachh-build/1.0"})
    with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)

    actual = digest(temporary)
    if actual != SHA256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"PANN checkpoint checksum mismatch: expected {SHA256}, got {actual}")
    temporary.replace(destination)
    print(f"PANN checkpoint verified: {destination}")


if __name__ == "__main__":
    main()
