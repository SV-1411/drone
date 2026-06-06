"""MAVLink connection layer with auto-retry and Python 3.10+ compatibility.

dronekit-python (2.9.2) was last released for Python 2/3.7. On 3.10+ it
crashes at import because ``collections.MutableMapping`` was relocated to
``collections.abc``. We patch the alias back before importing dronekit so
the high-level Vehicle API still works.
"""
from __future__ import annotations

import collections
import collections.abc
import logging
import math
import time
from typing import Optional

# ---- Python 3.10+ shim for dronekit ----------------------------------------
for _name in ("MutableMapping", "Mapping", "Iterable", "Callable", "Sequence", "Set"):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))
# ----------------------------------------------------------------------------

from dronekit import connect, Vehicle, LocationGlobalRelative, LocationGlobal  # noqa: E402

log = logging.getLogger("flight_core.mavlink")


def connect_vehicle(
    connection_string: str,
    timeout_s: int = 90,
    retries: int = 5,
    backoff_s: float = 3.0,
) -> Vehicle:
    """Connect to the vehicle, retrying on failure with exponential-ish backoff."""
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            log.info("MAVLink connect attempt %d/%d -> %s", attempt, retries, connection_string)
            vehicle = connect(connection_string, wait_ready=True, timeout=timeout_s, heartbeat_timeout=timeout_s)
            log.info("MAVLink connected: firmware=%s mode=%s", vehicle.version, vehicle.mode.name)
            return vehicle
        except Exception as exc:  # dronekit raises a mix of exception types
            last_err = exc
            log.warning("Connect attempt %d failed: %s", attempt, exc)
            time.sleep(backoff_s * attempt)
    raise RuntimeError(f"Could not connect to MAVLink at {connection_string}: {last_err}")


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def relative_location(vehicle: Vehicle) -> Optional[LocationGlobalRelative]:
    loc = vehicle.location.global_relative_frame
    if loc is None or loc.lat is None or loc.lon is None:
        return None
    return loc


def global_location(vehicle: Vehicle) -> Optional[LocationGlobal]:
    loc = vehicle.location.global_frame
    if loc is None or loc.lat is None or loc.lon is None:
        return None
    return loc


def wait_for_gps_lock(vehicle: Vehicle, min_sats: int = 6, timeout_s: int = 60) -> bool:
    """Block until the vehicle reports a usable GPS fix or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        gps = vehicle.gps_0
        if gps is not None and gps.fix_type is not None and gps.fix_type >= 3 and (gps.satellites_visible or 0) >= min_sats:
            log.info("GPS lock acquired: fix=%s sats=%s", gps.fix_type, gps.satellites_visible)
            return True
        time.sleep(0.5)
    log.error("GPS lock timeout after %ss", timeout_s)
    return False
