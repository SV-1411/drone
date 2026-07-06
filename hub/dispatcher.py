"""Dispatcher — hands a confirmed incident to the drone stack's trigger API."""
from __future__ import annotations

import logging
from typing import Optional

import requests

from .config import HubConfig

log = logging.getLogger("hub.dispatcher")


class Dispatcher:
    def __init__(self, config: HubConfig):
        self.config = config

    def dispatch(self, lat: float, lon: float, priority: str,
                 node_name: str = "") -> Optional[str]:
        """POST /trigger. Returns the mission id, or None on failure."""
        payload = {
            "lat": lat,
            "lon": lon,
            "priority": priority,
            "incident_type": "acoustic_distress",
            "deliver_kit": True,
        }
        headers = {}
        if self.config.drone_api_token:
            headers["X-API-Key"] = self.config.drone_api_token
        url = f"{self.config.drone_api_url}/trigger"
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
        except requests.RequestException as exc:
            log.error("drone API unreachable: %s", exc)
            return None
        if r.status_code == 429:
            log.error("drone queue full — incident logged but NOT dispatched")
            return None
        if not r.ok:
            log.error("dispatch rejected (%d): %s", r.status_code, r.text[:200])
            return None
        mission_id = r.json().get("mission_id")
        log.info("drone dispatched: mission=%s -> (%.6f, %.6f) [%s] %s",
                 mission_id, lat, lon, priority, node_name)
        return mission_id
