"""Failsafe monitor: battery, GPS, geofence, mission timeout.

Runs in a background thread alongside the mission executor. When a failsafe
fires it sets ``triggered`` and a reason; the executor checks these between
phases and aborts to RTL/LAND as appropriate.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .config import Config
from .mavlink_interface import haversine_distance_m

log = logging.getLogger("flight_core.failsafe")


@dataclass
class FailsafeEvent:
    name: str
    reason: str
    at: float = field(default_factory=time.time)
    action: str = "RTL"  # RTL | LAND | NONE


class FailsafeHandler:
    """Polls the vehicle on a fixed cadence; raises failsafe events."""

    def __init__(self, vehicle, config: Config, mission_started_at: float):
        self.vehicle = vehicle
        self.config = config
        self.mission_started_at = mission_started_at
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._events: List[FailsafeEvent] = []
        self._lock = threading.Lock()
        self.triggered: bool = False
        self.required_action: str = "NONE"

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="failsafe-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def events(self) -> List[FailsafeEvent]:
        with self._lock:
            return list(self._events)

    def _emit(self, ev: FailsafeEvent) -> None:
        with self._lock:
            self._events.append(ev)
            if not self.triggered or ev.action == "LAND":
                self.triggered = True
                self.required_action = ev.action
        log.error("FAILSAFE: %s — %s -> %s", ev.name, ev.reason, ev.action)

    def _run(self) -> None:
        cfg = self.config
        while not self._stop.is_set():
            try:
                self._check_battery()
                self._check_gps()
                self._check_geofence()
                self._check_timeout()
            except Exception:  # never let the monitor die
                log.exception("Failsafe monitor iteration failed")
            time.sleep(1.0)

    def _check_battery(self) -> None:
        bat = self.vehicle.battery
        if bat is None or bat.level is None:
            return
        if bat.level <= self.config.critical_battery_pct:
            self._emit(FailsafeEvent("critical_battery", f"battery {bat.level}% <= {self.config.critical_battery_pct}%", action="LAND"))
        elif bat.level <= self.config.low_battery_pct and not self.triggered:
            self._emit(FailsafeEvent("low_battery", f"battery {bat.level}% <= {self.config.low_battery_pct}%", action="RTL"))

    def _check_gps(self) -> None:
        gps = self.vehicle.gps_0
        if gps is None or gps.fix_type is None or gps.fix_type < 2:
            self._emit(FailsafeEvent("gps_loss", f"fix_type={getattr(gps,'fix_type',None)} sats={getattr(gps,'satellites_visible',None)}", action="LAND"))

    def _check_geofence(self) -> None:
        loc = self.vehicle.location.global_relative_frame
        if loc is None or loc.lat is None or loc.lon is None:
            return
        dist = haversine_distance_m(self.config.home_lat, self.config.home_lon, loc.lat, loc.lon)
        if dist > self.config.geofence_radius_m:
            self._emit(FailsafeEvent("geofence_breach", f"distance {dist:.0f}m > radius {self.config.geofence_radius_m:.0f}m", action="RTL"))

    def _check_timeout(self) -> None:
        if time.time() - self.mission_started_at > self.config.max_mission_duration_s:
            self._emit(FailsafeEvent("mission_timeout", f"mission running > {self.config.max_mission_duration_s}s", action="RTL"))
