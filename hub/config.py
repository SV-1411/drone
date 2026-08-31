"""Hub configuration — env-driven, mirroring flight_core.config style."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


DEFAULT_DRONE_BASES = (
    ("Vasudev Nagar Metro (West)", 21.1188, 79.0195),
    ("Sadar (North)", 21.1720, 79.0900),
    ("Pardi (East)", 21.1500, 79.1300),
    ("Manish Nagar (South)", 21.0930, 79.0680),
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
    drone_api_url: str = "http://127.0.0.1:8000"
    drone_api_token: str = ""
    master_key_hex: str = "000102030405060708090a0b0c0d0e0f"
    nodes_file: str = os.path.join(os.path.dirname(__file__), "nodes.json")
    clips_dir: str = os.path.join(os.path.dirname(__file__), "clips")
    serial_port: str = "COM3"
    serial_baud: int = 115200

    # Stage 2 — PANN verification on the Raspberry Pi 5.
    verify_threshold: float = 0.70
    min_positive_frames: int = 3
    # Render does not ship the large PANN checkpoint.  Its Stage-2 fallback is
    # the committed YAMNet TFLite model, which has a separately calibrated
    # AudioSet probability scale.
    yamnet_verify_threshold: float = 0.30
    yamnet_min_positive_frames: int = 3
    dispatch_threshold: float = 0.60
    clip_wait_s: float = 8.0
    clip_server_port: int = 8990
    # Optional path to the already-trained PANN checkpoint on the Pi 5.
    # When unset, panns-inference uses its normal checkpoint resolution.
    pann_checkpoint_path: str = ""
    pann_device: str = "cpu"

    test_lat: float = 21.1466
    test_lon: float = 79.0889
    base_lat: float = 21.1188
    base_lon: float = 79.0195
    drone_speed_ms: float = 15.0
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
            verify_threshold=_env_float("VERIFY_THRESHOLD", 0.70),
            min_positive_frames=int(os.environ.get("MIN_DISTRESS_FRAMES", "3")),
            yamnet_verify_threshold=_env_float("YAMNET_VERIFY_THRESHOLD", 0.30),
            yamnet_min_positive_frames=int(os.environ.get("YAMNET_MIN_DISTRESS_FRAMES", "3")),
            dispatch_threshold=_env_float("DISPATCH_THRESHOLD", 0.60),
            clip_wait_s=_env_float("CLIP_WAIT_S", 8.0),
            clip_server_port=int(os.environ.get("PORT", os.environ.get("CLIP_SERVER_PORT", "8990"))),
            pann_checkpoint_path=os.environ.get("PANN_CHECKPOINT_PATH", ""),
            pann_device=os.environ.get("PANN_DEVICE", "cpu"),
            test_lat=_env_float("TEST_LAT", 21.1466),
            test_lon=_env_float("TEST_LON", 79.0889),
            base_lat=_env_float("BASE_LAT", 21.1188),
            base_lon=_env_float("BASE_LON", 79.0195),
            drone_speed_ms=_env_float("DRONE_SPEED", 15.0),
            drone_bases=_env_bases("DRONE_BASES", DEFAULT_DRONE_BASES),
        )


CONFIG = HubConfig.from_env()
