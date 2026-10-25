"""Generate one Ed25519 device key; print only its public key."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from Crypto.PublicKey import ECC


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("private_key_path", type=Path)
    args = parser.parse_args()
    path = args.private_key_path
    path.parent.mkdir(parents=True, exist_ok=True)
    key = ECC.generate(curve="Ed25519")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as output:
            output.write(key.export_key(format="PEM"))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    print(key.public_key().export_key(format="PEM"))


if __name__ == "__main__":
    main()
