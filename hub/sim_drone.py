"""A simulated drone for phone-only / no-hardware testing.

The simulator keeps the SAME geographic route and cruise speed used for the
real-time ETA, but accelerates wall-clock playback so a presentation remains
watchable. It never uses a fixed 5-13 second flight time: longer geographic
routes always take proportionally longer in the simulation.

The real flight logic still lives in flight_core and is validated in ArduPilot
SITL; this module is the deployed visual/integration simulator.
"""
from __future__ import annotations

import math
import os
import threading
import time


def _haversine_m(a, b) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0]); dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


# Presentation playback is accelerated, but DISTANCE / SPEED still determine
# the mission. At 15 m/s, a 1 km route is ~67 real seconds and ~6.7 simulated
# seconds; a 10,000 km route is ~185 real hours and ~18.5 simulated minutes.
# The acceleration only changes wall-clock playback, never the reported ETA.
SIM_TIME_ACCEL = max(1.0, float(os.environ.get("SIM_TIME_ACCEL", "600")))
HOVER_S = 2.0
DROP_S = 2.0


class SimDrone:
    def __init__(self, base_lat=21.1800, base_lon=79.1100, speed_ms=15.0, name="Base"):
        self._lock = threading.Lock()
        self._counter = 0
        self._gen = 0
        self.base = (base_lat, base_lon)
        self.base_name = name
        self.speed = max(1.0, speed_ms)
        self._reset()

    def _reset(self):
        with self._lock:
            self.state = "IDLE"
            self.mission_id = None
            self.lat, self.lon = self.base
            self.target = None
            self.kit_dropped = False
            self.node_name = ""
            self.eta_reach_s = 0.0
            self.distance_m = 0.0
            self.flight_duration_sim_s = 0.0

    def snapshot(self) -> dict:
        with self._lock:
            at_base = self.state in ("IDLE", "COMPLETED", "FAILED")
            return {
                "state": self.state, "mission_id": self.mission_id,
                "name": self.base_name,
                "location_name": self.base_name if at_base else "en route",
                "lat": self.lat, "lon": self.lon,
                "home": [self.base[0], self.base[1]],
                "base_name": self.base_name, "target": self.target,
                "available": at_base, "kit_dropped": self.kit_dropped,
                "node_name": self.node_name,
                "eta_reach_s": round(self.eta_reach_s),
                "distance_m": round(self.distance_m),
                "sim_time_accel": SIM_TIME_ACCEL,
                "flight_duration_sim_s": round(self.flight_duration_sim_s, 1),
            }

    def eta(self, lat, lon) -> dict:
        """Real-world ETA at the configured cruise speed, never accelerated."""
        with self._lock:
            frm = (self.lat, self.lon)
        dist = _haversine_m(frm, (lat, lon))
        reach = dist / self.speed
        return {
            "distance_m": round(dist),
            "eta_reach_s": round(reach),
            "eta_total_s": round(reach + HOVER_S + DROP_S),
        }

    def busy(self) -> bool:
        with self._lock:
            return self.state not in ("IDLE", "COMPLETED", "FAILED")

    def dispatch(self, lat: float, lon: float, priority: str = "high",
                 node_name: str = "") -> str | None:
        """Dispatch from the drone's CURRENT position to the geographic target."""
        with self._lock:
            self._counter += 1
            self._gen += 1
            gen = self._gen
            mid = f"sim{self._counter:04d}"
            frm = (self.lat if self.lat is not None else self.base[0],
                   self.lon if self.lon is not None else self.base[1])
            dist = _haversine_m(frm, (lat, lon))
            real_flight_s = dist / self.speed
            sim_flight_s = real_flight_s / SIM_TIME_ACCEL
            self.mission_id = mid
            self.target = [lat, lon]
            self.kit_dropped = False
            self.node_name = node_name
            self.state = "TAKEOFF"
            self.distance_m = dist
            self.eta_reach_s = real_flight_s
            self.flight_duration_sim_s = sim_flight_s

        threading.Thread(
            target=self._run,
            args=(frm, (lat, lon), mid, gen, dist, sim_flight_s),
            name="sim-drone", daemon=True,
        ).start()
        return mid

    def _set(self, gen, **kw):
        with self._lock:
            if self._gen != gen:
                return False
            for k, v in kw.items():
                setattr(self, k, v)
            return True

    def _leg(self, gen, a, b, dur, state):
        if not self._set(gen, state=state):
            return
        dur = max(0.25, float(dur))
        t0 = time.time()
        while True:
            f = min(1.0, (time.time() - t0) / dur)
            if not self._set(
                gen,
                lat=a[0] + (b[0] - a[0]) * f,
                lon=a[1] + (b[1] - a[1]) * f,
            ):
                return
            if f >= 1.0:
                return
            time.sleep(0.1)

    def _run(self, frm, target, mid, gen, dist, sim_flight_s):
        if not self._set(gen, state="TAKEOFF"):
            return
        time.sleep(min(1.0, max(0.3, 2.0 / SIM_TIME_ACCEL + 0.4)))
        self._leg(gen, frm, target, sim_flight_s, "ENROUTE")
        if not self._set(gen, state="HOVERING"):
            return
        time.sleep(HOVER_S)
        if not self._set(gen, state="DELIVERING"):
            return
        time.sleep(DROP_S)
        if not self._set(gen, kit_dropped=True):
            return
        time.sleep(0.5)
        back = _haversine_m(target, self.base)
        back_sim_s = (back / self.speed) / SIM_TIME_ACCEL
        self._leg(gen, target, self.base, back_sim_s, "RTL")
        self._set(gen, state="COMPLETED")


class SimDispatcher:
    def __init__(self, drone: SimDrone):
        self.drone = drone

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        return self.drone.dispatch(lat, lon, priority, node_name)


class DroneFleet:
    """Several drones parked at prime-location stations.

    The nearest station is selected using the geographic haversine distance.
    Mission playback then follows the actual geographic distance and configured
    cruise speed, with only the wall-clock presentation accelerated.
    """

    def __init__(self, bases, speed_ms=15.0):
        self.drones = [SimDrone(la, lo, speed_ms, name=nm) for nm, la, lo in bases]

    def _nearest(self, lat, lon):
        best, best_d = None, None
        for d in self.drones:
            dist = _haversine_m(d.base, (lat, lon))
            if best_d is None or dist < best_d:
                best, best_d = d, dist
        return best, best_d

    def eta(self, lat, lon) -> dict:
        drone, _ = self._nearest(lat, lon)
        e = drone.eta(lat, lon)
        e["drone"] = drone.base_name
        return e

    def dispatch(self, lat, lon, priority="high", node_name="") -> str | None:
        drone, _ = self._nearest(lat, lon)
        self.last_drone = drone.base_name
        return drone.dispatch(lat, lon, priority, node_name)

    def active(self) -> dict:
        flying = [d for d in self.drones if not d.snapshot()["available"]]
        return (flying[-1] if flying else self.drones[0]).snapshot()

    def snapshots(self) -> list:
        return [d.snapshot() for d in self.drones]


class FleetDispatcher:
    def __init__(self, fleet: "DroneFleet"):
        self.fleet = fleet

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        return self.fleet.dispatch(lat, lon, priority, node_name)


class PhoneDrone:
    """A second phone playing the drone for multi-phone demos."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.lat = self.lon = None
            self.state = "IDLE"
            self.target = None
            self.mission_id = None
            self.kit_dropped = False
            self.ts = 0.0
            self.node_name = ""

    def assign(self, lat, lon, mission_id, node_name=""):
        with self._lock:
            self.target = [lat, lon]
            self.mission_id = mission_id
            self.node_name = node_name
            self.kit_dropped = False
            if self.state in ("IDLE", "COMPLETED"):
                self.state = "DISPATCHED"

    def report(self, lat, lon, state=None, kit=None):
        with self._lock:
            self.lat, self.lon = lat, lon
            if state:
                self.state = state
            if kit is not None:
                self.kit_dropped = bool(kit)
            self.ts = time.time()

    def fresh(self, within=15.0) -> bool:
        with self._lock:
            return self.lat is not None and (time.time() - self.ts) < within

    def mission(self) -> dict:
        with self._lock:
            return {"mission_id": self.mission_id, "target": self.target,
                    "has_mission": self.target is not None}

    def snapshot(self) -> dict:
        with self._lock:
            return {"state": self.state, "mission_id": self.mission_id,
                    "lat": self.lat, "lon": self.lon, "home": None,
                    "target": self.target, "kit_dropped": self.kit_dropped,
                    "node_name": self.node_name, "source": "phone"}
