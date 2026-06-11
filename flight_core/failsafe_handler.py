"""Failsafe monitor: battery, GPS, geofence, mission timeout.

Runs in a background thread alongside the mission executor. When a failsafe
fires it sets ``triggered`` and a reason; the executor checks these between
phases and aborts to RTL/LAND as appropriate.

Design rules:
- Each named failsafe fires at most once per mission (no event/log spam),
  except that a LAND-severity event can still escalate over an earlier
  RTL-severity one.
- GPS loss is debounced: it takes ``config.gps_bad_samples_to_trigger``
  consecutive bad 1 Hz samples to fire, so a single-sample glitch never
  puts the aircraft down.
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

MAX_EVENTS = 100


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
        self._fired_names: set = set()
        self._gps_bad_streak = 0
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
            # Fire each named failsafe once; allow re-fire only when escalating
            # an already-fired name from RTL to LAND severity.
            already = ev.name in self._fired_names
            if already and ev.action != "LAND":
                return
            if already and self.required_action == "LAND":
                return
            self._fired_names.add(ev.name)
            self._events.append(ev)
            if len(self._events) > MAX_EVENTS:
                self._events = self._events[-MAX_EVENTS:]
            self.triggered = True
            # LAND outranks RTL; never downgrade.
            if self.required_action != "LAND":
                self.required_action = ev.action
        log.error("FAILSAFE: %s — %s -> %s", ev.name, ev.reason, ev.action)

    def _run(self) -> None:
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
        elif bat.level <= self.config.low_battery_pct:
            self._emit(FailsafeEvent("low_battery", f"battery {bat.level}% <= {self.config.low_battery_pct}%", action="RTL"))

    def _check_gps(self) -> None:
        gps = self.vehicle.gps_0
        bad = gps is None or gps.fix_type is None or gps.fix_type < 2
        if not bad:
            self._gps_bad_streak = 0
            return
        self._gps_bad_streak += 1
        if self._gps_bad_streak >= self.config.gps_bad_samples_to_trigger:
            # With no GPS, RTL cannot navigate — LAND in place is the only
            # safe autonomous response.
            self._emit(FailsafeEvent(
                "gps_loss",
                f"fix_type={getattr(gps, 'fix_type', None)} for {self._gps_bad_streak} consecutive samples",
                action="LAND",
            ))

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
