"""A simulated drone for phone-only / no-hardware testing.

Lets you exercise the whole pipeline (phone -> hub -> detection -> dispatch ->
response) with nothing but a browser. When a dispatch happens, this animates a
mission (arm, take off, fly to the incident, hover, drop the kit, return) and
publishes its moving position so the dashboard can draw it on the map.

This is a visualisation of the response for testing. The real flight logic lives
in flight_core and is validated in SITL; this is only for the phone demo.
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


class SimDrone:
    ANIM_MIN_S = 5.0       # on-screen flight is compressed to this range so a
    ANIM_MAX_S = 13.0      # demo is watchable; the ETA shown is the REAL time.
    HOVER_S = 2.0
    DROP_S = 2.0

    def __init__(self, base_lat=21.1800, base_lon=79.1100, speed_ms=15.0):
        self._lock = threading.Lock()
        self._counter = 0
        self._gen = 0                     # bumped per dispatch; old missions self-cancel
        self.base = (base_lat, base_lon)
        self.speed = max(1.0, speed_ms)   # m/s, for the real ETA
        self._reset()

    def _reset(self):
        with self._lock:
            self.state = "IDLE"
            self.mission_id = None
            self.lat, self.lon = self.base       # parked at the station
            self.target = None
            self.kit_dropped = False
            self.node_name = ""
            self.eta_reach_s = 0.0
            self.distance_m = 0.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self.state, "mission_id": self.mission_id,
                "lat": self.lat, "lon": self.lon,
                "home": [self.base[0], self.base[1]], "target": self.target,
                "kit_dropped": self.kit_dropped, "node_name": self.node_name,
                "eta_reach_s": round(self.eta_reach_s),
                "distance_m": round(self.distance_m),
            }

    def eta(self, lat, lon) -> dict:
        """Real time to reach (lat, lon) from where the drone is now, plus the
        hover+drop time, at the configured cruise speed."""
        with self._lock:
            frm = (self.lat, self.lon)
        dist = _haversine_m(frm, (lat, lon))
        reach = dist / self.speed
        return {"distance_m": round(dist), "eta_reach_s": round(reach),
                "eta_total_s": round(reach + self.HOVER_S + self.DROP_S)}

    def busy(self) -> bool:
        with self._lock:
            return self.state not in ("IDLE", "COMPLETED", "FAILED")

    def dispatch(self, lat: float, lon: float, priority: str = "high",
                 node_name: str = "") -> str | None:
        """Fly from the drone's current position to (lat, lon). A new alert
        cancels the running mission and flies from wherever it is now (no
        teleport). Returns the new mission id."""
        with self._lock:
            self._counter += 1
            self._gen += 1
            gen = self._gen
            mid = f"sim{self._counter:04d}"
            frm = (self.lat if self.lat is not None else self.base[0],
                   self.lon if self.lon is not None else self.base[1])
            dist = _haversine_m(frm, (lat, lon))
            self.mission_id = mid
            self.target = [lat, lon]
            self.kit_dropped = False
            self.node_name = node_name
            self.state = "TAKEOFF"
            self.distance_m = dist
            self.eta_reach_s = dist / self.speed
        threading.Thread(target=self._run, args=(frm, (lat, lon), mid, gen, dist),
                         name="sim-drone", daemon=True).start()
        return mid

    def _set(self, gen, **kw):
        """Update state only if this mission is still the current one."""
        with self._lock:
            if self._gen != gen:
                return False
            for k, v in kw.items():
                setattr(self, k, v)
            return True

    def _anim(self, dist):
        return max(self.ANIM_MIN_S, min(self.ANIM_MAX_S, dist / self.speed))

    def _leg(self, gen, a, b, dur, state):
        if not self._set(gen, state=state):
            return
        t0 = time.time()
        while True:
            f = min(1.0, (time.time() - t0) / dur)
            if not self._set(gen, lat=a[0] + (b[0] - a[0]) * f,
                             lon=a[1] + (b[1] - a[1]) * f):
                return                     # superseded by a newer mission
            if f >= 1.0:
                return
            time.sleep(0.2)

    def _run(self, frm, target, mid, gen, dist):
        if not self._set(gen, state="TAKEOFF"): return
        time.sleep(1.0)
        self._leg(gen, frm, target, self._anim(dist), "ENROUTE")   # fly the real path
        if not self._set(gen, state="HOVERING"): return
        time.sleep(self.HOVER_S)
        if not self._set(gen, state="DELIVERING"): return
        time.sleep(self.DROP_S)
        self._set(gen, kit_dropped=True); time.sleep(1.0)
        back = _haversine_m(target, self.base)
        self._leg(gen, target, self.base, self._anim(back), "RTL")  # return to station
        self._set(gen, state="COMPLETED")


class SimDispatcher:
    """Drop-in replacement for hub.dispatcher.Dispatcher that drives a SimDrone
    instead of POSTing to a real drone API. Same dispatch() signature."""

    def __init__(self, drone: SimDrone):
        self.drone = drone

    def dispatch(self, lat, lon, priority="normal", node_name=""):
        return self.drone.dispatch(lat, lon, priority, node_name)


class PhoneDrone:
    """A second phone playing the drone. It is assigned the incident location,
    then reports its own GPS as it physically moves toward the spot. The
    dashboard draws that movement live. This makes a real multi-phone demo
    without any aircraft."""

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
        """A new incident to respond to."""
        with self._lock:
            self.target = [lat, lon]
            self.mission_id = mission_id
            self.node_name = node_name
            self.kit_dropped = False
            if self.state in ("IDLE", "COMPLETED"):
                self.state = "DISPATCHED"

    def report(self, lat, lon, state=None, kit=None):
        """The drone phone posts its GPS (and optionally a state change)."""
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
