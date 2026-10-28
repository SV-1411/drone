"""Poll the verified Render queue and hand a nearby incident to the local flight API.

The Pi is the only MAVLink owner. This process never opens the Pixhawk serial
port itself and never sends arm/mode/motor commands. The local flight API keeps
its independent physical-dispatch lock and mission/failsafe state machine.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from device_signatures import sign_headers

LOG = logging.getLogger("drone_pi_cloud_bridge")
RELAY_URL = os.environ.get("VANNI_RELAY_URL", "https://vannikawachh-hub.onrender.com").rstrip("/")
API_URL = os.environ.get("VANNI_FLIGHT_API_URL", "http://127.0.0.1:8000").rstrip("/")
RELAY_TOKEN = os.environ.get("VANNI_DRONE_ESP_TOKEN", "")
SIGNING_KEY_PATH = os.environ.get(
    "VANNI_DRONE_SIGNING_KEY", "/home/vannidrone/.config/vannikawachh/drone-pi-signing.pem")
API_TOKEN = os.environ.get("VANNI_FLIGHT_API_TOKEN", "")
CLAIM_ENABLED = os.environ.get("VANNI_CLOUD_CLAIM_ENABLED", "") == "1"
PILOT_READY = os.environ.get("VANNI_PILOT_READY", "") == "1"


def request_json(url: str, *, payload: dict | None = None,
                 token: str = "", api_key: str = "", signing_key: str = "") -> dict:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    if api_key:
        headers["X-API-Key"] = api_key
    method = "GET" if body is None else "POST"
    if signing_key:
        parsed = urlparse(url)
        target = parsed.path + (("?" + parsed.query) if parsed.query else "")
        headers.update(sign_headers(signing_key, method, target, body or b""))
    req = Request(url, body, headers=headers, method=method)
    with urlopen(req, timeout=8) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = a2 - a1, math.radians(lon2 - lon1)
    term = math.sin(dlat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2) ** 2
    return 12_742_000 * math.asin(min(1, math.sqrt(term)))


def readiness(health: dict, telemetry: dict, target: tuple[float, float] | None = None,
              *, check_home: bool = True) -> str | None:
    """Fail closed on stale, implausible or insufficient aircraft telemetry."""
    if not health.get("vehicle_connected") or health.get("state") != "IDLE":
        return "Pixhawk is disconnected or mission executor is busy"
    limits = health.get("flight_limits") or {}
    if not limits.get("allow_real_dispatch") or not health.get("auth_enabled"):
        return "local flight API is locked or has no API key"
    if not (1 <= float(limits.get("cruise_altitude_m", 999)) <= 3 and
            0.1 <= float(limits.get("cruise_speed_ms", 999)) <= 1 and
            float(limits.get("max_mission_duration_s", 9999)) <= 180 and
            float(limits.get("geofence_radius_m", 9999)) <= 60):
        return "prototype speed, altitude, duration or geofence limits are not set"
    if telemetry.get("armed") or telemetry.get("state") != "IDLE":
        return "aircraft is armed or busy"
    if time.time() - float(telemetry.get("timestamp", 0)) > 5:
        return "autopilot telemetry is stale"
    if int(telemetry.get("gps_fix") or 0) < 3 or int(telemetry.get("gps_sats") or 0) < 8:
        return "3D GPS fix with eight satellites is required"
    voltage, percent = telemetry.get("battery_voltage"), telemetry.get("battery_pct")
    if (voltage is None or percent is None or not 6 <= float(voltage) <= 60 or
            not 30 <= float(percent) <= 100):
        return "usable battery telemetry is required"
    try:
        lat, lon = float(telemetry.get("lat")), float(telemetry.get("lon"))
    except (TypeError, ValueError):
        return "aircraft coordinates are unavailable"
    if not all(map(math.isfinite, (lat, lon))) or (lat == 0 and lon == 0):
        return "aircraft position is invalid"
    if check_home:
        try:
            home_lat = float(telemetry.get("home_lat"))
            home_lon = float(telemetry.get("home_lon"))
        except (TypeError, ValueError):
            return "launch-home coordinates are unavailable"
        if not all(map(math.isfinite, (home_lat, home_lon))):
            return "launch-home coordinates are invalid"
        if telemetry.get("home_source") != "captured":
            return "launch home has not been captured from grounded Pixhawk GPS"
        try:
            age = time.time() - float(telemetry.get("home_captured_at"))
        except (TypeError, ValueError):
            age = float("inf")
        if not 0 <= age <= 15:
            return "launch home is stale; capture live grounded Pixhawk GPS again"
        if distance_m(lat, lon, home_lat, home_lon) > 8:
            return "aircraft moved from freshly captured launch home"
    if target is not None:
        tlat, tlon = target
        if (not all(map(math.isfinite, target)) or not -90 <= tlat <= 90 or
                not -180 <= tlon <= 180 or (tlat == 0 and tlon == 0)):
            return "target coordinates are invalid"
        if distance_m(lat, lon, tlat, tlon) > 30:
            return "target is beyond the 30 m supervised test radius"
    return None


def local_state() -> tuple[dict, dict]:
    return request_json(API_URL + "/health"), request_json(API_URL + "/telemetry")


def report(command_id: str, status: str, detail: str) -> None:
    path = "/edge/drone/result/" + quote(command_id, safe="")
    request_json(RELAY_URL + path, payload={"status": status, "detail": detail[:240]},
                 signing_key=SIGNING_KEY_PATH)


def process(command: dict) -> None:
    command_id = str(command.get("id", ""))
    if not command_id:
        raise ValueError("claimed command has no ID")
    try:
        target = (float(command["lat"]), float(command["lon"]))
        health, telemetry = local_state()
        reason = readiness(health, telemetry, target)
        if reason:
            report(command_id, "rejected", reason)
            LOG.warning("Rejected %s: %s", command_id, reason)
            return
        incident_type = ("operator_test" if command.get("node_id") == "operator-test"
                         else "verified_acoustic_distress")
        payload = {"lat": target[0], "lon": target[1],
                   "incident_type": incident_type, "priority": "high",
                   "deliver_kit": False, "hover_s": 0}
        result = request_json(API_URL + "/trigger", payload=payload, api_key=API_TOKEN)
        if result.get("status") != "queued" or not result.get("mission_id"):
            raise ValueError("flight API did not confirm queue acceptance")
        report(command_id, "mission_queued", "local mission " + str(result["mission_id"]))
        LOG.info("Local flight API queued %s for cloud command %s", result["mission_id"], command_id)
    except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as exc:
        LOG.exception("Cloud command %s failed", command_id)
        try:
            report(command_id, "failed", type(exc).__name__)
        except (HTTPError, URLError, OSError, ValueError):
            LOG.error("Could not report failure for %s; no duplicate claim will be made", command_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parsed_relay = urlparse(RELAY_URL)
    parsed_api = urlparse(API_URL)
    if parsed_relay.scheme != "https" or parsed_api.hostname not in ("127.0.0.1", "localhost"):
        raise SystemExit("relay must use HTTPS and flight API must be localhost")
    if not os.path.isfile(SIGNING_KEY_PATH):
        raise SystemExit("drone signing key is missing")
    if CLAIM_ENABLED and (len(API_TOKEN) < 32 or not PILOT_READY):
        raise SystemExit("claim mode requires local API key and pilot readiness")
    LOG.info("Pi cloud bridge online; claim mode %s", "enabled" if CLAIM_ENABLED else "locked")
    last_notice = ""
    while True:
        try:
            health, telemetry = local_state()
            state = "Pixhawk=%s GPS=%s/%s flight_lock=%s" % (
                "connected" if health.get("vehicle_connected") else "disconnected",
                telemetry.get("gps_fix"), telemetry.get("gps_sats"),
                not (health.get("flight_limits") or {}).get("allow_real_dispatch"))
            if state != last_notice:
                LOG.info(state)
                last_notice = state
            request_json(RELAY_URL + "/edge/drone/telemetry",
                         signing_key=SIGNING_KEY_PATH,
                         payload={"heartbeat": bool(health.get("vehicle_connected")),
                                  "gps_fix": int(telemetry.get("gps_fix") or 0),
                                  "satellites": int(telemetry.get("gps_sats") or 0),
                                  "armed": bool(telemetry.get("armed")),
                                  "mission_state": str(telemetry.get("state", "unknown"))})
            if CLAIM_ENABLED and readiness(health, telemetry, check_home=False) is None:
                if readiness(health, telemetry) is not None:
                    request_json(API_URL + "/home/capture", payload={}, api_key=API_TOKEN)
                    health, telemetry = local_state()
            if CLAIM_ENABLED and readiness(health, telemetry) is None:
                claimed = request_json(RELAY_URL + "/edge/drone/claim/next",
                                       signing_key=SIGNING_KEY_PATH, payload={}).get("command")
                if claimed:
                    process(claimed)
        except (HTTPError, URLError, OSError, ValueError, TypeError) as exc:
            LOG.warning("bridge polling unavailable: %s", type(exc).__name__)
        time.sleep(3)


if __name__ == "__main__":
    main()
