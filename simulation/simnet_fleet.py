"""Adapter that gives the existing hub dispatch API a SIMNET backend."""
from __future__ import annotations

import math
import threading

from .simnet_bridge import SimnetMavlinkBridge


class SimnetFleet:
    def __init__(self, bases, speed_ms=15.0):
        if not bases:
            raise ValueError("At least one base is required")
        self.base = bases[0]
        self.speed_ms = max(1.0, float(speed_ms))
        self.bridge = SimnetMavlinkBridge()
        self.counter = 0

    def _distance(self, lat, lon):
        a = (self.base[1], self.base[2])
        b = (float(lat), float(lon))
        r = 6_371_000.0
        p1, p2 = math.radians(a[0]), math.radians(b[0])
        dp = math.radians(b[0] - a[0])
        dl = math.radians(b[1] - a[1])
        x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(max(0.0, x)))

    def eta(self, lat, lon):
        d = self._distance(lat, lon)
        return {
            "drone": self.base[0],
            "distance_m": round(d),
            "eta_reach_s": round(d / self.speed_ms),
            "eta_total_s": round(d / self.speed_ms + 14),
        }

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        self.counter += 1
        mission_id = f"simnet{self.counter:04d}"
        t = threading.Thread(
            target=self.bridge.mission,
            args=(mission_id, float(lat), float(lon), 3),
            daemon=True,
            name="simnet-mission",
        )
        t.start()
        return mission_id

    def active(self):
        s = self.bridge.snapshot()
        s.update({
            "name": self.base[0],
            "home": [self.base[1], self.base[2]],
            "base_name": self.base[0],
            "available": not s.get("armed", False) and s.get("state") in ("DISCONNECTED", "COMPLETED", "FAILED", "IDLE"),
            "distance_m": 0,
            "eta_reach_s": 0,
        })
        return s

    def snapshots(self):
        return [self.active()]

    def close(self):
        self.bridge.close()
