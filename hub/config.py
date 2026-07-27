"""Hub configuration — env-driven, mirroring flight_core.config style."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
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
    # The ETA shown is the real time to fly base -> incident at this speed.
    base_lat: float = 21.1051       # G H Raisoni College of Engineering, Nagpur
    base_lon: float = 79.0036
    drone_speed_ms: float = 15.0    # ~54 km/h cruise (typical delivery quadcopter)

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
        )


CONFIG = HubConfig.from_env()
