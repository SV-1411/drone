"""A simulated drone for phone-only / no-hardware testing.

The simulator follows the actual geographic route at the configured cruise speed.
Wall-clock playback is deliberately fixed at 1x so distance, speed, telemetry and
visible movement remain physically interpretable in the presentation.
"""
from __future__ import annotations

import math
import threading
import time


def _haversine_m(a, b) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0]); dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


SIM_TIME_ACCEL = 1.0
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
            flying = self.state in ("TAKEOFF", "ENROUTE", "HOVERING", "DELIVERING", "RTL")
            altitude = 15.0 if self.state in ("ENROUTE", "HOVERING", "DELIVERING", "RTL") else (5.0 if self.state == "TAKEOFF" else 0.0)
            speed = self.speed if self.state in ("ENROUTE", "RTL") else (3.0 if self.state == "TAKEOFF" else 0.0)
            return {
                "state": self.state,
                "mission_id": self.mission_id,
                "name": self.base_name,
                "location_name": self.base_name if at_base else "en route",
                "lat": self.lat,
                "lon": self.lon,
                "home": [self.base[0], self.base[1]],
                "base_name": self.base_name,
                "target": self.target,
                "available": at_base,
                "kit_dropped": self.kit_dropped,
                "node_name": self.node_name,
                "eta_reach_s": round(self.eta_reach_s),
                "distance_m": round(self.distance_m),
                "speed_ms": round(speed, 2),
                "altitude_m": round(altitude, 1),
                "motors_active": flying,
                "sim_time_accel": 1.0,
                "flight_duration_sim_s": round(self.flight_duration_sim_s, 1),
            }

    def eta(self, lat, lon) -> dict:
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

    def recall(self) -> str:
        """Recall this drone to its base.  Returns a status string.

        - If the drone is already at base (IDLE/COMPLETED/FAILED) → 'at_base'.
        - If the drone is mid-flight → abort current leg, fly RTL to base.
        """
        with self._lock:
            if self.state in ("IDLE", "COMPLETED", "FAILED"):
                return "at_base"
            # Bump generation so the current _run thread exits.
            self._gen += 1
            gen = self._gen
            frm = (self.lat, self.lon)
        # Start RTL in a background thread (same pattern as dispatch).
        back = _haversine_m(frm, self.base)
        threading.Thread(
            target=self._recall_run,
            args=(frm, gen, back / self.speed),
            name="sim-drone-recall",
            daemon=True,
        ).start()
        return "returning"

    def _recall_run(self, frm, gen, dur):
        """Fly the drone back to base after a recall."""
        if not self._set(gen, state="RTL"):
            return
        self._leg(gen, frm, self.base, dur, "RTL")
        self._set(gen, state="COMPLETED", mission_id=None, target=None,
                  kit_dropped=False, node_name="")

    def dispatch(self, lat: float, lon: float, priority: str = "high", node_name: str = "") -> str | None:
        with self._lock:
            self._counter += 1
            self._gen += 1
            gen = self._gen
            mid = f"sim{self._counter:04d}"
            frm = (self.lat if self.lat is not None else self.base[0],
                   self.lon if self.lon is not None else self.base[1])
            dist = _haversine_m(frm, (lat, lon))
            real_flight_s = dist / self.speed
            self.mission_id = mid
            self.target = [lat, lon]
            self.kit_dropped = False
            self.node_name = node_name
            self.state = "TAKEOFF"
            self.distance_m = dist
            self.eta_reach_s = real_flight_s
            self.flight_duration_sim_s = real_flight_s

        threading.Thread(
            target=self._run,
            args=(frm, (lat, lon), gen, real_flight_s),
            name="sim-drone",
            daemon=True,
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

    def _run(self, frm, target, gen, flight_s):
        if not self._set(gen, state="TAKEOFF"):
            return
        time.sleep(1.5)
        self._leg(gen, frm, target, flight_s, "ENROUTE")
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
        self._leg(gen, target, self.base, back / self.speed, "RTL")
        self._set(gen, state="COMPLETED")


class SimDispatcher:
    def __init__(self, drone: SimDrone):
        self.drone = drone

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        return self.drone.dispatch(lat, lon, priority, node_name)


class DroneFleet:
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

    def recall_by_name(self, name: str) -> str | None:
        """Recall a specific drone by its base_name.  Returns the recall
        status string ('returning' or 'at_base'), or None if not found."""
        for d in self.drones:
            if d.base_name == name:
                return d.recall()
        return None


class FleetDispatcher:
    def __init__(self, fleet: "DroneFleet"):
        self.fleet = fleet

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        return self.fleet.dispatch(lat, lon, priority, node_name)


class PhoneDrone:
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
