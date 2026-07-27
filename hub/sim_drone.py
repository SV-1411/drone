"""A simulated drone for phone-only / no-hardware testing.

Lets you exercise the whole pipeline (phone -> hub -> detection -> dispatch ->
response) with nothing but a browser. When a dispatch happens, this animates a
mission (arm, take off, fly to the incident, hover, drop the kit, return) and
publishes its moving position so the dashboard can draw it on the map.

This is a visualisation of the response for testing. The real flight logic lives
in flight_core and is validated in SITL; this is only for the phone demo.
"""
from __future__ import annotations

import threading
import time


class SimDrone:
    ENROUTE_S = 9.0        # seconds to fly home -> target (compressed for demo)
    RTL_S = 9.0
    BASE_OFFSET = 0.005    # ~550 m north of the incident = the drone's "base"

    def __init__(self):
        self._lock = threading.Lock()
        self._counter = 0
        self._gen = 0            # bumped on each dispatch; old missions self-cancel
        self._reset()

    def _reset(self):
        with self._lock:
            self.state = "IDLE"
            self.mission_id = None
            self.lat = self.lon = None
            self.home = self.target = None
            self.kit_dropped = False
            self.node_name = ""

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self.state, "mission_id": self.mission_id,
                "lat": self.lat, "lon": self.lon,
                "home": self.home, "target": self.target,
                "kit_dropped": self.kit_dropped, "node_name": self.node_name,
            }

    def busy(self) -> bool:
        with self._lock:
            return self.state not in ("IDLE", "COMPLETED", "FAILED")

    def dispatch(self, lat: float, lon: float, priority: str = "high",
                 node_name: str = "") -> str | None:
        """Respond to (lat, lon). A new alert cancels any running mission and
        flies to the new spot, so triggering from a different location always
        moves the drone. Returns the new mission id."""
        with self._lock:
            self._counter += 1
            self._gen += 1                 # cancels any in-flight mission
            gen = self._gen
            mid = f"sim{self._counter:04d}"
            home = (lat + self.BASE_OFFSET, lon)
            self.mission_id = mid
            self.home = [home[0], home[1]]
            self.target = [lat, lon]
            self.lat, self.lon = home
            self.kit_dropped = False
            self.node_name = node_name
            self.state = "ARMING"
        threading.Thread(target=self._run, args=(home, (lat, lon), mid, gen),
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

    def _run(self, home, target, mid, gen):
        if not self._set(gen, state="ARMING"): return
        time.sleep(1.2)
        if not self._set(gen, state="TAKEOFF"): return
        time.sleep(1.8)
        self._leg(gen, home, target, self.ENROUTE_S, "ENROUTE")
        if not self._set(gen, state="HOVERING"): return
        time.sleep(2.5)
        if not self._set(gen, state="DELIVERING"): return
        time.sleep(2.0)
        self._set(gen, kit_dropped=True); time.sleep(1.5)
        self._leg(gen, target, home, self.RTL_S, "RTL")
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
