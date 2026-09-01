"""Presentation-grade physical drone simulator for VanniKawachh.

Models the mission as a real sequence instead of a teleport:
ARMING -> TAKEOFF -> ENROUTE -> HOVERING -> DELIVERING -> RTL -> LANDING -> COMPLETED.
The browser layer consumes this telemetry; true flight dynamics remain ArduPilot SITL/Gazebo.
"""
from __future__ import annotations

import math
import threading
import time


def haversine_m(a, b):
    R = 6_371_000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(max(0.0, x)))


def bearing(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    return (math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                    math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) + 360) % 360


def interp(a, b, f):
    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f


def rpm_for_state(state: str) -> float:
    return {
        "IDLE": 0.0,
        "ARMING": 0.0,
        "TAKEOFF": 4200.0,
        "ENROUTE": 5000.0,
        "HOVERING": 4300.0,
        "DELIVERING": 3800.0,
        "RTL": 5000.0,
        "LANDING": 2600.0,
        "COMPLETED": 0.0,
        "FAILED": 0.0,
    }.get(state, 0.0)


class PhysicalSimDrone:
    def __init__(self, base_lat, base_lon, speed_ms=15.0, name="Base"):
        self.lock = threading.RLock()
        self.base = (float(base_lat), float(base_lon))
        self.speed = max(1.0, float(speed_ms))
        self.name = name
        self.counter = 0
        self.generation = 0
        self.state = "IDLE"
        self.mission_id = None
        self.lat, self.lon = self.base
        self.altitude_m = 0.0
        self.ground_speed_ms = 0.0
        self.heading_deg = 0.0
        self.target = None
        self.kit_dropped = False
        self.node_name = ""
        self.started_at = None
        self.eta_reach_s = 0.0
        self.distance_m = 0.0
        self.battery_pct = 100.0

    def snapshot(self):
        with self.lock:
            rpm = rpm_for_state(self.state)
            armed = self.state in {"TAKEOFF", "ENROUTE", "HOVERING", "DELIVERING", "RTL", "LANDING"}
            return {
                "state": self.state,
                "flight_mode": self.state,
                "armed": armed,
                "motor_rpm": rpm,
                "motor_channels": [rpm, rpm, -rpm, -rpm] if rpm else [0, 0, 0, 0],
                "mission_id": self.mission_id,
                "name": self.name,
                "location_name": self.name if self.state in ("IDLE", "COMPLETED") else "en route",
                "lat": self.lat,
                "lon": self.lon,
                "home": [self.base[0], self.base[1]],
                "base_name": self.name,
                "target": self.target,
                "available": self.state in ("IDLE", "COMPLETED", "FAILED"),
                "kit_dropped": self.kit_dropped,
                "node_name": self.node_name,
                "eta_reach_s": round(max(0.0, self.eta_reach_s)),
                "distance_m": round(max(0.0, self.distance_m)),
                "speed_ms": round(self.ground_speed_ms, 2),
                "ground_speed_ms": round(self.ground_speed_ms, 2),
                "altitude_m": round(self.altitude_m, 2),
                "heading_deg": round(self.heading_deg, 1),
                "battery_pct": round(self.battery_pct, 1),
                "flight_elapsed_s": round(time.time() - self.started_at, 1) if self.started_at else 0.0,
            }

    def recall(self) -> str:
        """Recall this drone to its base."""
        with self.lock:
            if self.state in ("IDLE", "COMPLETED", "FAILED"):
                return "at_base"
            self.generation += 1
            generation = self.generation
            frm = (self.lat, self.lon)
        back = haversine_m(frm, self.base)
        threading.Thread(
            target=self._recall_run, args=(frm, generation, back / self.speed),
            daemon=True, name="physical-drone-recall",
        ).start()
        return "returning"

    def _recall_run(self, frm, generation, dur):
        self._set(generation, state="RTL", target=None, mission_id=None,
                  kit_dropped=False, node_name="")
        self._travel(generation, frm, self.base, dur, "RTL", 15.0)
        self._set(generation, state="LANDING", ground_speed_ms=0.0,
                  distance_m=0, eta_reach_s=0)
        self._climb(generation, 0.0, 4.0)
        self._set(generation, state="COMPLETED", lat=self.base[0], lon=self.base[1],
                  altitude_m=0.0, ground_speed_ms=0.0, distance_m=0, eta_reach_s=0)

    def dispatch(self, lat, lon, priority="high", node_name=""):
        with self.lock:
            if self.state not in ("IDLE", "COMPLETED", "FAILED"):
                return self.mission_id
            self.counter += 1
            self.generation += 1
            generation = self.generation
            self.mission_id = f"sim{self.counter:04d}"
            self.target = [float(lat), float(lon)]
            self.node_name = node_name
            self.kit_dropped = False
            self.started_at = time.time()
            self.state = "ARMING"
            self.ground_speed_ms = 0.0
            self.altitude_m = 0.0
            self.heading_deg = bearing((self.lat, self.lon), (float(lat), float(lon)))
            self.distance_m = haversine_m((self.lat, self.lon), (float(lat), float(lon)))
            self.eta_reach_s = self.distance_m / self.speed + 7.0
            self.battery_pct = 100.0
        threading.Thread(target=self._run, args=(generation,), daemon=True, name="physical-drone").start()
        return self.mission_id

    def _active(self, generation):
        with self.lock:
            return self.generation == generation

    def _set(self, generation, **kw):
        with self.lock:
            if self.generation != generation:
                return False
            for k, v in kw.items():
                setattr(self, k, v)
            return True

    def _climb(self, generation, target_alt, seconds=4.0):
        t0 = time.time()
        start_alt = self.altitude_m
        while True:
            f = min(1.0, (time.time() - t0) / seconds)
            alt = start_alt + (target_alt - start_alt) * f
            self._set(generation, altitude_m=alt, ground_speed_ms=0.0)
            if f >= 1.0:
                break
            time.sleep(0.05)

    def _travel(self, generation, start, end, seconds, state, altitude):
        seconds = max(2.0, float(seconds))
        t0 = time.time()
        while True:
            f = min(1.0, (time.time() - t0) / seconds)
            lat, lon = interp(start, end, f)
            left = haversine_m((lat, lon), end)
            self._set(generation,
                      lat=lat,
                      lon=lon,
                      altitude_m=altitude,
                      ground_speed_ms=self.speed,
                      heading_deg=bearing(start, end),
                      state=state,
                      distance_m=left,
                      eta_reach_s=left / self.speed)
            if f >= 1.0:
                break
            time.sleep(0.05)

    def _run(self, generation):
        target = tuple(self.target)
        cruise_alt = 15.0
        outbound = haversine_m((self.lat, self.lon), target)
        outbound_s = outbound / self.speed
        try:
            time.sleep(1.2)
            if not self._set(generation, state="TAKEOFF"):
                return
            self._climb(generation, cruise_alt, 4.0)
            if not self._active(generation):
                return

            self._travel(generation, (self.base[0], self.base[1]), target, outbound_s, "ENROUTE", cruise_alt)
            if not self._active(generation):
                return

            self._set(generation, state="HOVERING", ground_speed_ms=0.0, distance_m=0, eta_reach_s=0)
            time.sleep(3.0)
            if not self._active(generation):
                return

            self._set(generation, state="DELIVERING", ground_speed_ms=0.0)
            time.sleep(2.0)
            if not self._active(generation):
                return
            self._set(generation, kit_dropped=True)
            time.sleep(1.0)

            home = self.base
            return_s = haversine_m(target, home) / self.speed
            self._travel(generation, target, home, return_s, "RTL", cruise_alt)
            if not self._active(generation):
                return

            self._set(generation, state="LANDING", ground_speed_ms=0.0, distance_m=0, eta_reach_s=0)
            self._climb(generation, 0.0, 4.0)
            if not self._active(generation):
                return
            self._set(generation, state="COMPLETED", lat=self.base[0], lon=self.base[1], altitude_m=0.0,
                      ground_speed_ms=0.0, distance_m=0, eta_reach_s=0)
        except Exception:
            self._set(generation, state="FAILED")


class PhysicalFleet:
    def __init__(self, bases, speed_ms=15.0):
        self.drones = [PhysicalSimDrone(la, lo, speed_ms, name=nm) for nm, la, lo in bases]
        self.last_drone = None

    def _nearest(self, lat, lon):
        return min(self.drones, key=lambda d: haversine_m(d.base, (lat, lon)))

    def eta(self, lat, lon):
        d = self._nearest(lat, lon)
        dist = haversine_m(d.base, (lat, lon))
        return {"drone": d.name, "distance_m": round(dist), "eta_reach_s": round(dist / d.speed),
                "eta_total_s": round(dist / d.speed + 7)}

    def dispatch(self, lat, lon, priority="high", node_name=""):
        d = self._nearest(lat, lon)
        self.last_drone = d.name
        return d.dispatch(lat, lon, priority, node_name)

    def active(self):
        active = [d for d in self.drones if not d.snapshot()["available"]]
        return (active[-1] if active else (self.drones[0] if self.drones else PhysicalSimDrone(21.1466, 79.0889))).snapshot()

    def snapshots(self):
        return [d.snapshot() for d in self.drones]

    def recall_by_name(self, name: str) -> str | None:
        """Recall a specific drone by its base_name."""
        for d in self.drones:
            if d.name == name:
                return d.recall()
        return None


class PhysicalDispatcher:
    def __init__(self, fleet):
        self.fleet = fleet

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        return self.fleet.dispatch(lat, lon, priority, node_name)
