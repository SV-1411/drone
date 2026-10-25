"""Signed device HTTP requests. Only public keys are stored in source."""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from pathlib import Path

from Crypto.PublicKey import ECC
from Crypto.Signature import eddsa

PUBLIC_KEYS = {
    "drone": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAFs4Ccwf5r6cQDTI9IJwSqvh6OzsoPOBHl0ZXV9CyUmA=\n-----END PUBLIC KEY-----",
    "sensing": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAdS9P7n9Bx2NlR2+s84K0oAtMexWNauBO9t0zSyVIfI8=\n-----END PUBLIC KEY-----",
}


def message(method: str, target: str, body: bytes, timestamp: str, nonce: str) -> bytes:
    digest = hashlib.sha256(body).hexdigest()
    return "\n".join((method.upper(), target, digest, timestamp, nonce)).encode("utf-8")


def sign_headers(private_key_path: str | Path, method: str,
                 target: str, body: bytes) -> dict[str, str]:
    timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
    key = ECC.import_key(Path(private_key_path).read_text(encoding="ascii"))
    signature = eddsa.new(key, "rfc8032").sign(
        message(method, target, body, timestamp, nonce))
    return {"X-Vanni-Timestamp": timestamp, "X-Vanni-Nonce": nonce,
            "X-Vanni-Signature": base64.b64encode(signature).decode("ascii")}


def verify_headers(role: str, method: str, target: str, body: bytes,
                   headers, *, now: float | None = None) -> str | None:
    """Return verified nonce or None. Caller must atomically reject replay."""
    timestamp = headers.get("X-Vanni-Timestamp", "")
    nonce = headers.get("X-Vanni-Nonce", "")
    signature = headers.get("X-Vanni-Signature", "")
    if (role not in PUBLIC_KEYS or not timestamp.isascii() or
            not timestamp.isdecimal() or len(timestamp) > 12 or
            len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce) or
            len(signature) > 100):
        return None
    if abs((time.time() if now is None else now) - int(timestamp)) > 120:
        return None
    try:
        raw = base64.b64decode(signature, validate=True)
        if len(raw) != 64:
            return None
        key = ECC.import_key(PUBLIC_KEYS[role])
        eddsa.new(key, "rfc8032").verify(
            message(method, target, body, timestamp, nonce), raw)
    except (ValueError, TypeError):
        return None
    return nonce
