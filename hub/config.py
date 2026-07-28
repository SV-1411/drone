"""Hub configuration — env-driven, mirroring flight_core.config style."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


# Prime-location drone stations. Each is (name, lat, lon). The response picks the
# station whose available drone is NEAREST the incident (see hub/sim_drone.py ->
# DroneFleet.dispatch / _nearest). Edit this list to place your drones, or set the
# DRONE_BASES env var to a JSON list like:
#   [["GHRCE",21.1051,79.0036],["Sitabuldi",21.1466,79.0889]]
DEFAULT_DRONE_BASES = (
    ("GHRCE (West)", 21.1051, 79.0036),         # west / Hingna side, project base
    ("Sadar (North)", 21.1720, 79.0900),        # north Nagpur
    ("Pardi (East)", 21.1500, 79.1300),         # east Nagpur
    ("Manish Nagar (South)", 21.0930, 79.0680),  # south Nagpur
)


def _env_bases(key: str, default):
    raw = os.environ.get(key)
    if not raw:
        return default
    try:
        return tuple((str(n), float(la), float(lo)) for n, la, lo in json.loads(raw))
    except Exception:
        return default


@dataclass(frozen=True)
class HubConfig:
    # Where the drone stack's trigger API lives
    drone_api_url: str = "http://127.0.0.1:8000"
    drone_api_token: str = ""            # X-API-Key if the API has auth enabled

    # AES-128 master key (hex, 32 chars). Per-node keys are derived from it.
    # The default is a DEV key — set HUB_MASTER_KEY in any real deployment.
    master_key_hex: str = "000102030405060708090a0b0c0d0e0f"

    # Node registry and clip storage
    nodes_file: str = os.path.join(os.path.dirname(__file__), "nodes.json")
    clips_dir: str = os.path.join(os.path.dirname(__file__), "clips")

    # Gateway serial port (the ESP32 LoRa gateway on USB)
    serial_port: str = "COM3"
    serial_baud: int = 115200

    # Stage-2 decision thresholds
    verify_threshold: float = 0.50       # min audio score to count as distress
    dispatch_threshold: float = 0.60     # min fused severity to launch the drone
    clip_wait_s: float = 8.0             # how long to wait for the WiFi clip

    # Clip upload server (nodes POST 4 s WAV clips here over WiFi/ESP-NOW bridge)
    clip_server_port: int = 8990

    # Phone-test default incident location (used when the phone can't share GPS,
    # e.g. over plain HTTP). Set to your test area.
    test_lat: float = 21.1466       # GHRCE Nagpur area
    test_lon: float = 79.0889

    # Drone base ("station") the response flies FROM, and its cruise speed.
    # base_lat/base_lon is the FIRST station and the map's default centre; the
    # full set of stations is drone_bases below.
    base_lat: float = 21.1051       # G H Raisoni College of Engineering, Nagpur
    base_lon: float = 79.0036
    drone_speed_ms: float = 15.0    # ~54 km/h cruise (typical delivery quadcopter)

    # All prime-location stations in the fleet, (name, lat, lon). The nearest
    # available drone to each incident is the one dispatched.
    drone_bases: tuple = DEFAULT_DRONE_BASES

    @classmethod
    def from_env(cls) -> "HubConfig":
        return cls(
            drone_api_url=os.environ.get("DRONE_API_URL", "http://127.0.0.1:8000"),
            drone_api_token=os.environ.get("DRONE_API_TOKEN", ""),
            master_key_hex=os.environ.get("HUB_MASTER_KEY", "000102030405060708090a0b0c0d0e0f"),
            nodes_file=os.environ.get("NODES_FILE", os.path.join(os.path.dirname(__file__), "nodes.json")),
            clips_dir=os.environ.get("CLIPS_DIR", os.path.join(os.path.dirname(__file__), "clips")),
            serial_port=os.environ.get("GATEWAY_PORT", "COM3"),
            serial_baud=int(os.environ.get("GATEWAY_BAUD", "115200")),
            verify_threshold=_env_float("VERIFY_THRESHOLD", 0.50),
            dispatch_threshold=_env_float("DISPATCH_THRESHOLD", 0.60),
            clip_wait_s=_env_float("CLIP_WAIT_S", 8.0),
            clip_server_port=int(os.environ.get("PORT", os.environ.get("CLIP_SERVER_PORT", "8990"))),
            test_lat=_env_float("TEST_LAT", 21.1466),
            test_lon=_env_float("TEST_LON", 79.0889),
            base_lat=_env_float("BASE_LAT", 21.1051),
            base_lon=_env_float("BASE_LON", 79.0036),
            drone_speed_ms=_env_float("DRONE_SPEED", 15.0),
            drone_bases=_env_bases("DRONE_BASES", DEFAULT_DRONE_BASES),
        )


CONFIG = HubConfig.from_env()
