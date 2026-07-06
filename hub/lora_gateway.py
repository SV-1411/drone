"""LoRa gateway readers.

The physical gateway is an ESP32+SX1278 (firmware/gateway/) plugged into the
Pi over USB; it prints one line per received frame:

    RX <hex-bytes> RSSI <dbm>

SerialGateway parses that stream. SimGateway is a drop-in used by tests and
the Phase-0 demo — packets are injected programmatically.
"""
from __future__ import annotations

import logging
import queue
from typing import Iterator, Optional

log = logging.getLogger("hub.gateway")


class SimGateway:
    """In-memory gateway for tests / the SITL demo."""

    def __init__(self):
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue()

    def inject(self, packet: bytes) -> None:
        self._q.put(packet)

    def close(self) -> None:
        self._q.put(None)

    def packets(self) -> Iterator[bytes]:
        while True:
            item = self._q.get()
            if item is None:
                return
            yield item


class SerialGateway:
    """Reads sealed packets from the gateway ESP32 on a serial port."""

    def __init__(self, port: str, baud: int = 115200):
        import serial  # pyserial — only needed for real hardware
        self._ser = serial.Serial(port, baud, timeout=1.0)
        log.info("gateway serial open on %s @ %d", port, baud)

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass

    def packets(self) -> Iterator[bytes]:
        while True:
            try:
                line = self._ser.readline().decode("ascii", "ignore").strip()
            except Exception as exc:
                log.error("serial read failed: %s", exc)
                return
            if not line.startswith("RX "):
                continue
            parts = line.split()
            try:
                pkt = bytes.fromhex(parts[1])
            except (IndexError, ValueError):
                log.warning("unparseable gateway line: %r", line)
                continue
            rssi = parts[3] if len(parts) >= 4 else "?"
            log.info("frame received (%d bytes, RSSI %s)", len(pkt), rssi)
            yield pkt
