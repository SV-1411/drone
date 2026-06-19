"""Map-based obstacle avoidance: route around known keep-out zones.

This is *deterministic, map-based* avoidance — it re-plans the horizontal path
around operator-configured cylindrical no-fly zones (a known-obstacle map). It
does **not** do sensor-based reactive avoidance (that needs a rangefinder /
depth camera + ArduPilot 4.x OA, and is on the roadmap); nothing here reads a
proximity sensor.

The geometry is pure and unit-testable without SITL. A leg that would pass
within ``radius + clearance`` of an obstacle centre is split with two detour
waypoints that carry the path around the zone at a safe lateral offset.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import List, Sequence, Tuple

_R = 6_371_000.0
LatLon = Tuple[float, float]


@dataclass(frozen=True)
class Obstacle:
    """A circular horizontal keep-out zone (cylinder, unbounded in altitude)."""
    lat: float
    lon: float
    radius_m: float
    name: str = "obstacle"


# ---- local-tangent-plane conversion (equirectangular, fine over a few km) ----
def _to_local(ref: LatLon, p: LatLon) -> Tuple[float, float]:
    east = math.radians(p[1] - ref[1]) * _R * math.cos(math.radians(ref[0]))
    north = math.radians(p[0] - ref[0]) * _R
    return east, north


def _to_global(ref: LatLon, east: float, north: float) -> LatLon:
    lat = ref[0] + math.degrees(north / _R)
    lon = ref[1] + math.degrees(east / (_R * math.cos(math.radians(ref[0]))))
    return lat, lon


def _closest(a, b, p) -> Tuple[float, float]:
    """Distance from point ``p`` to segment ``a-b`` and the (unclamped) projection
    parameter ``t`` along the segment."""
    abx, aby = b[0] - a[0], b[1] - a[1]
    l2 = abx * abx + aby * aby
    if l2 == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1]), 0.0
    t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / l2
    tc = max(0.0, min(1.0, t))
    cx, cy = a[0] + tc * abx, a[1] + tc * aby
    return math.hypot(p[0] - cx, p[1] - cy), t


def path_clear(start: LatLon, end: LatLon, obstacles: Sequence[Obstacle],
               clearance_m: float) -> bool:
    """True if the straight leg start->end stays clear of every obstacle."""
    a = (0.0, 0.0)
    b = _to_local(start, end)
    for o in obstacles:
        c = _to_local(start, (o.lat, o.lon))
        dist, _ = _closest(a, b, c)
        if dist < o.radius_m + clearance_m:
            return False
    return True


def _first_blocking(start: LatLon, end: LatLon, obstacles: Sequence[Obstacle],
                    clearance_m: float):
    """The obstacle the leg hits earliest along its length (or None)."""
    a = (0.0, 0.0)
    b = _to_local(start, end)
    hit = None
    best_t = math.inf
    for o in obstacles:
        c = _to_local(start, (o.lat, o.lon))
        dist, t = _closest(a, b, c)
        if dist < o.radius_m + clearance_m and 0.0 < t < 1.0 and t < best_t:
            best_t, hit = t, (o, c, b)
    return hit


def plan_route(start: LatLon, end: LatLon, obstacles: Sequence[Obstacle],
               clearance_m: float = 8.0, _depth: int = 0) -> List[LatLon]:
    """Return the list of waypoints (excluding ``start``, ending at ``end``)
    that carries the path from ``start`` to ``end`` around the obstacles.

    With no obstacles in the way this is simply ``[end]`` — identical to flying
    direct, so behaviour is unchanged when no map is configured.
    """
    if _depth >= 6 or not obstacles:
        return [end]
    blocking = _first_blocking(start, end, obstacles, clearance_m)
    if blocking is None:
        return [end]

    o, c, b = blocking
    length = math.hypot(b[0], b[1])
    if length == 0.0:
        return [end]
    u = (b[0] / length, b[1] / length)                 # along-path unit
    t = max(0.0, min(1.0, (c[0] * u[0] + c[1] * u[1]) / length))
    proj = (t * b[0], t * b[1])                        # closest path point to centre
    # perpendicular, pointing from the centre toward the path (bulge to that side)
    px, py = proj[0] - c[0], proj[1] - c[1]
    pmag = math.hypot(px, py)
    n = (px / pmag, py / pmag) if pmag > 1e-6 else (-u[1], u[0])

    offset = o.radius_m + clearance_m + max(3.0, clearance_m * 0.5)
    along = o.radius_m + clearance_m                   # stand off before/after
    wp1 = (proj[0] - u[0] * along + n[0] * offset, proj[1] - u[1] * along + n[1] * offset)
    wp2 = (proj[0] + u[0] * along + n[0] * offset, proj[1] + u[1] * along + n[1] * offset)
    g1 = _to_global(start, *wp1)
    g2 = _to_global(start, *wp2)

    # Recurse on the approach and the departure so other obstacles are handled.
    approach = plan_route(start, g1, obstacles, clearance_m, _depth + 1)
    depart = plan_route(g2, end, obstacles, clearance_m, _depth + 1)
    return approach + [g2] + depart


def load_obstacles_from_env(var: str = "OBSTACLES") -> List[Obstacle]:
    """Parse obstacles from an env var holding JSON, e.g.
    ``[{"lat":28.617,"lon":77.211,"radius":120,"name":"tower"}]`` or
    ``[[28.617,77.211,120]]``. Returns [] if unset or malformed."""
    raw = os.environ.get(var, "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    out: List[Obstacle] = []
    for item in data:
        try:
            if isinstance(item, dict):
                out.append(Obstacle(float(item["lat"]), float(item["lon"]),
                                    float(item.get("radius", item.get("radius_m"))),
                                    str(item.get("name", "obstacle"))))
            else:
                out.append(Obstacle(float(item[0]), float(item[1]), float(item[2]),
                                    str(item[3]) if len(item) > 3 else "obstacle"))
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return out
