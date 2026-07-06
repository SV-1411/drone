"""LoRa alert packet format + AES-128 sealing.

A spoofed packet would launch a drone, so every packet is sealed:
AES-128-CTR for confidentiality + truncated HMAC-SHA256 for authenticity,
with a per-node monotonic counter for replay protection.

Wire format (25 bytes total — comfortably one LoRa frame):

    offset  size  field
    0       2     magic  b"VK"
    2       1     version (1)
    3       2     node_id (uint16 BE)          -- cleartext (selects the key)
    5       4     counter (uint32 BE)          -- cleartext (CTR nonce + replay)
    9       8     ciphertext of payload:
                      event    uint8   (1=scream 2=help_keyword 3=cry 4=crash)
                      conf     uint8   (stage-1 confidence 0..255)
                      pir      uint8   (0/1)
                      light    uint8   (LDR level 0..255, 0 = dark)
                      battery  uint8   (%)
                      reserved 3 bytes
    17      8     MAC: HMAC-SHA256(node_key, header+ciphertext)[:8]

Per-node key = HMAC-SHA256(master_key, b"node:%d")[:16] — so provisioning a
node needs only the master key and its id.
"""
from __future__ import annotations

import hmac
import hashlib
import struct
from dataclasses import dataclass
from typing import Optional

from Crypto.Cipher import AES

MAGIC = b"VK"
VERSION = 1
PACKET_LEN = 25

EVENT_NAMES = {1: "scream", 2: "help_keyword", 3: "cry", 4: "crash"}


@dataclass
class Alert:
    node_id: int
    counter: int
    event: int
    confidence: float        # 0.0 .. 1.0 (from the stage-1 model)
    pir: bool
    light: int               # 0..255, low = dark
    battery_pct: int

    @property
    def event_name(self) -> str:
        return EVENT_NAMES.get(self.event, f"unknown({self.event})")


def node_key(master_key: bytes, node_id: int) -> bytes:
    return hmac.new(master_key, b"node:%d" % node_id, hashlib.sha256).digest()[:16]


def _ctr_cipher(key: bytes, node_id: int, counter: int):
    # 16-byte nonce/IV derived from the cleartext header — unique per packet
    # as long as the counter is monotonic per node.
    iv = struct.pack(">2sBHI7x", MAGIC, VERSION, node_id, counter)
    return AES.new(key, AES.MODE_CTR, nonce=b"", initial_value=iv)


def seal(master_key: bytes, alert: Alert) -> bytes:
    """Build the sealed wire packet for an alert (what a node transmits)."""
    key = node_key(master_key, alert.node_id)
    header = struct.pack(">2sBHI", MAGIC, VERSION, alert.node_id, alert.counter)
    payload = struct.pack(
        ">BBBBB3x",
        alert.event,
        max(0, min(255, int(round(alert.confidence * 255)))),
        1 if alert.pir else 0,
        max(0, min(255, alert.light)),
        max(0, min(100, alert.battery_pct)),
    )
    ct = _ctr_cipher(key, alert.node_id, alert.counter).encrypt(payload)
    mac = hmac.new(key, header + ct, hashlib.sha256).digest()[:8]
    return header + ct + mac


class PacketError(ValueError):
    pass


def unseal(master_key: bytes, packet: bytes,
           last_counter: Optional[int] = None) -> Alert:
    """Verify + decrypt a wire packet. Raises PacketError on any problem."""
    if len(packet) != PACKET_LEN:
        raise PacketError(f"bad length {len(packet)}")
    magic, version, node_id, counter = struct.unpack(">2sBHI", packet[:9])
    if magic != MAGIC or version != VERSION:
        raise PacketError("bad magic/version")
    key = node_key(master_key, node_id)
    header, ct, mac = packet[:9], packet[9:17], packet[17:25]
    expect = hmac.new(key, header + ct, hashlib.sha256).digest()[:8]
    if not hmac.compare_digest(mac, expect):
        raise PacketError(f"bad MAC from node {node_id}")
    if last_counter is not None and counter <= last_counter:
        raise PacketError(f"replayed counter {counter} (last {last_counter}) from node {node_id}")
    payload = _ctr_cipher(key, node_id, counter).decrypt(ct)
    event, conf, pir, light, battery = struct.unpack(">BBBBB3x", payload)
    return Alert(
        node_id=node_id, counter=counter, event=event,
        confidence=conf / 255.0, pir=bool(pir), light=light, battery_pct=battery,
    )
