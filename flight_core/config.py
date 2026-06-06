"""Central configuration for the drone safety system.

All values can be overridden via environment variables so the same code runs
identically in native Windows mode and inside Docker.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    # MAVLink connection — SITL defaults to tcp:127.0.0.1:5760
    mavlink_connection: str = os.environ.get("MAVLINK_CONNECTION", "tcp:127.0.0.1:5760")
    connect_timeout_s: int = _env_int("MAVLINK_CONNECT_TIMEOUT", 90)
    connect_retries: int = _env_int("MAVLINK_CONNECT_RETRIES", 5)

    # Home base (the spawn point in SITL). Defaults match the brief: New Delhi.
    home_lat: float = _env_float("HOME_LAT", 28.6139)
    home_lon: float = _env_float("HOME_LON", 77.2090)
    home_alt: float = _env_float("HOME_ALT", 0.0)

    # Default mission parameters
    default_target_lat: float = _env_float("TARGET_LAT", 28.6200)
    default_target_lon: float = _env_float("TARGET_LON", 77.2150)
    cruise_altitude_m: float = _env_float("CRUISE_ALT", 15.0)
    hover_duration_s: int = _env_int("HOVER_DURATION", 30)
    waypoint_tolerance_m: float = _env_float("WAYPOINT_TOLERANCE", 5.0)

    # Failsafes
    low_battery_pct: float = _env_float("LOW_BATTERY_PCT", 20.0)
    critical_battery_pct: float = _env_float("CRIT_BATTERY_PCT", 10.0)
    geofence_radius_m: float = _env_float("GEOFENCE_RADIUS", 5000.0)
    max_mission_duration_s: int = _env_int("MAX_MISSION_DURATION", 1800)

    # API
    api_host: str = os.environ.get("API_HOST", "0.0.0.0")
    api_port: int = _env_int("API_PORT", 8000)
    telemetry_interval_ms: int = _env_int("TELEMETRY_INTERVAL_MS", 500)

    # Logging
    log_dir: str = os.environ.get("LOG_DIR", "logs")


CONFIG = Config()
