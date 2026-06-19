"""Unit tests for map-based obstacle avoidance — pure geometry, no SITL."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flight_core.obstacle_avoidance import (
    Obstacle, path_clear, plan_route, load_obstacles_from_env,
    _to_local, _to_global,
)

HOME = (28.6139, 77.2090)
TARGET = (28.6139, 77.2290)        # ~2 km due east of home


def _legs(start, route):
    pts = [start] + route
    return list(zip(pts[:-1], pts[1:]))


def test_local_global_roundtrip():
    p = (28.6200, 77.2150)
    e, n = _to_local(HOME, p)
    back = _to_global(HOME, e, n)
    assert abs(back[0] - p[0]) < 1e-7
    assert abs(back[1] - p[1]) < 1e-7


def test_clear_path_returns_direct():
    # obstacle well to the north of the east-bound path -> no detour
    obs = [Obstacle(28.6250, 77.2190, 100.0, "north")]
    assert path_clear(HOME, TARGET, obs, clearance_m=10.0)
    assert plan_route(HOME, TARGET, obs, clearance_m=10.0) == [TARGET]


def test_blocking_obstacle_is_detected():
    mid = (28.6139, 77.2190)            # right on the path
    obs = [Obstacle(mid[0], mid[1], 120.0, "tower")]
    assert not path_clear(HOME, TARGET, obs, clearance_m=20.0)


def test_route_clears_blocking_obstacle():
    mid = (28.6139, 77.2190)
    clearance = 20.0
    obs = [Obstacle(mid[0], mid[1], 120.0, "tower")]
    route = plan_route(HOME, TARGET, obs, clearance_m=clearance)
    assert len(route) > 1                       # a detour was inserted
    assert route[-1] == TARGET                  # still ends at the target
    # every leg of the planned route must clear every obstacle
    for a, b in _legs(HOME, route):
        assert path_clear(a, b, obs, clearance_m=clearance), f"leg {a}->{b} not clear"


def test_route_clears_two_obstacles():
    clearance = 15.0
    obs = [
        Obstacle(28.6139, 77.2160, 90.0, "a"),
        Obstacle(28.6139, 77.2230, 90.0, "b"),
    ]
    route = plan_route(HOME, TARGET, obs, clearance_m=clearance)
    assert route[-1] == TARGET
    for a, b in _legs(HOME, route):
        assert path_clear(a, b, obs, clearance_m=clearance)


def test_load_obstacles_from_env_dict(monkeypatch):
    monkeypatch.setenv("OBSTACLES", '[{"lat":28.62,"lon":77.21,"radius":120,"name":"x"}]')
    obs = load_obstacles_from_env()
    assert len(obs) == 1 and obs[0].radius_m == 120.0 and obs[0].name == "x"


def test_load_obstacles_from_env_list_and_bad():
    os.environ["OBSTACLES"] = '[[28.62,77.21,80]]'
    obs = load_obstacles_from_env()
    assert len(obs) == 1 and obs[0].radius_m == 80.0
    os.environ["OBSTACLES"] = "not json"
    assert load_obstacles_from_env() == []
    del os.environ["OBSTACLES"]
    assert load_obstacles_from_env() == []
