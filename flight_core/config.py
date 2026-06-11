"""Central configuration for the drone safety system.

All values can be overridden via environment variables so the same code runs
identically in native Windows mode and inside Docker.

Env vars are read in :meth:`Config.from_env` at construction time (not at
import time), so tests and embedders can set ``os.environ`` and then build a
fresh ``Config`` — or pass explicit kwargs and bypass the environment
entirely.
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
    mavlink_connection: str = "tcp:127.0.0.1:5760"
    connect_timeout_s: int = 90
    connect_retries: int = 5

    # Home base (the spawn point in SITL). Defaults match the brief: New Delhi.
    home_lat: float = 28.6139
    home_lon: float = 77.2090
    home_alt: float = 0.0

    # Default mission parameters
    default_target_lat: float = 28.6200
    default_target_lon: float = 77.2150
    cruise_altitude_m: float = 15.0
    cruise_speed_ms: float = 8.0
    hover_duration_s: int = 30
    waypoint_tolerance_m: float = 5.0

    # Mission sanity bounds (enforced at the API surface)
    min_altitude_m: float = 2.0
    max_altitude_m: float = 120.0  # regulatory AGL ceiling in most jurisdictions
    max_hover_s: int = 3600

    # Failsafes
    low_battery_pct: float = 20.0
    critical_battery_pct: float = 10.0
    geofence_radius_m: float = 5000.0
    max_mission_duration_s: int = 1800
    gps_bad_samples_to_trigger: int = 3  # consecutive 1 Hz samples before GPS failsafe
    leg_stall_timeout_s: float = 45.0    # abort a leg if no progress for this long

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    telemetry_interval_ms: int = 500
    api_token: str = ""          # empty = auth disabled (SITL/dev); set API_TOKEN in prod
    max_queue_depth: int = 20
    history_limit: int = 1000

    # Logging / persistence
    log_dir: str = "logs"
    db_path: str = ""            # empty = default to <log_dir>/missions.db

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            mavlink_connection=os.environ.get("MAVLINK_CONNECTION", "tcp:127.0.0.1:5760"),
            connect_timeout_s=_env_int("MAVLINK_CONNECT_TIMEOUT", 90),
            connect_retries=_env_int("MAVLINK_CONNECT_RETRIES", 5),
            home_lat=_env_float("HOME_LAT", 28.6139),
            home_lon=_env_float("HOME_LON", 77.2090),
            home_alt=_env_float("HOME_ALT", 0.0),
            default_target_lat=_env_float("TARGET_LAT", 28.6200),
            default_target_lon=_env_float("TARGET_LON", 77.2150),
            cruise_altitude_m=_env_float("CRUISE_ALT", 15.0),
            cruise_speed_ms=_env_float("CRUISE_SPEED", 8.0),
            hover_duration_s=_env_int("HOVER_DURATION", 30),
            waypoint_tolerance_m=_env_float("WAYPOINT_TOLERANCE", 5.0),
            min_altitude_m=_env_float("MIN_ALTITUDE", 2.0),
            max_altitude_m=_env_float("MAX_ALTITUDE", 120.0),
            max_hover_s=_env_int("MAX_HOVER", 3600),
            low_battery_pct=_env_float("LOW_BATTERY_PCT", 20.0),
            critical_battery_pct=_env_float("CRIT_BATTERY_PCT", 10.0),
            geofence_radius_m=_env_float("GEOFENCE_RADIUS", 5000.0),
            max_mission_duration_s=_env_int("MAX_MISSION_DURATION", 1800),
            gps_bad_samples_to_trigger=_env_int("GPS_BAD_SAMPLES", 3),
            leg_stall_timeout_s=_env_float("LEG_STALL_TIMEOUT", 45.0),
            api_host=os.environ.get("API_HOST", "0.0.0.0"),
            api_port=_env_int("API_PORT", 8000),
            telemetry_interval_ms=_env_int("TELEMETRY_INTERVAL_MS", 500),
            api_token=os.environ.get("API_TOKEN", ""),
            max_queue_depth=_env_int("MAX_QUEUE_DEPTH", 20),
            history_limit=_env_int("HISTORY_LIMIT", 1000),
            log_dir=os.environ.get("LOG_DIR", "logs"),
            db_path=os.environ.get("DB_PATH", ""),
        )

    @property
    def resolved_db_path(self) -> str:
        return self.db_path or os.path.join(self.log_dir, "missions.db")


CONFIG = Config.from_env()
