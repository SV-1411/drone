"""Adapter that makes the existing VanniKawachh dispatch API drive SIMNET."""
from __future__ import annotations

import threading
import time

from .simnet_bridge import SimnetMavlinkBridge, _haversine


class SimnetFleetAdapter:
    def __init__(self, fallback_fleet, bridge: SimnetMavlinkBridge):
        self.fallback = fallback_fleet
        self.bridge = bridge
        self.last_mission = None

    def eta(self, lat, lon):
        snap = self.bridge.snapshot()
        if snap.get("connected") and snap.get("lat") is not None:
            dist = _haversine(snap["lat"], snap["lon"], lat, lon)
            return {
                "drone": "SIMNET F450",
                "distance_m": round(dist),
                "eta_reach_s": round(dist / 12.0),
                "eta_total_s": round(dist / 12.0 + 14),
            }
        return self.fallback.eta(lat, lon)

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        mission_id = self.bridge.state.mission_id or f"simnet-{int(time.time())}"
        self.last_mission = mission_id

        def run():
            ok = self.bridge.mission(mission_id, float(lat), float(lon), hover_s=3)
            if not ok:
                return

        threading.Thread(target=run, daemon=True, name="simnet-mission").start()
        return mission_id

    def active(self):
        snap = self.bridge.snapshot()
        if snap.get("connected") or snap.get("mission_id"):
            return snap
        return self.fallback.active()

    def snapshots(self):
        snap = self.bridge.snapshot()
        if snap.get("connected") or snap.get("mission_id"):
            return [snap]
        return self.fallback.snapshots()


class SimnetDispatcher:
    def __init__(self, fleet: SimnetFleetAdapter):
        self.fleet = fleet

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        return self.fleet.dispatch(lat, lon, priority, node_name)
