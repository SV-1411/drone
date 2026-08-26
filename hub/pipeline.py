"""Alert pipeline — the hub's decision chain for one incoming packet.

    sealed packet ─▶ unseal (AES+MAC+replay) ─▶ registry lookup
                  ─▶ wait for WiFi clip ─▶ Stage-2 verify ─▶ fuse evidence
                  ─▶ dispatch decision ─▶ drone + dashboard log
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .config import HubConfig
from .dispatcher import Dispatcher
from .fusion import fuse
from .node_registry import NodeRegistry
from .packets import Alert, PacketError, unseal
from .verifier import Stage2Verifier

log = logging.getLogger("hub.pipeline")


@dataclass
class Incident:
    alert: Alert
    node_name: str
    lat: float
    lon: float
    audio_score: float
    severity: float
    priority: str
    dispatched: bool
    mission_id: Optional[str]
    reasons: str
    audio_analysis: Optional[dict] = None
    confirmation_reasons: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    ts: float = field(default_factory=time.time)


class AlertPipeline:
    def __init__(self, config: HubConfig, registry: NodeRegistry,
                 verifier: Optional[Stage2Verifier] = None,
                 dispatcher: Optional[Dispatcher] = None):
        self.config = config
        self.registry = registry
        self.verifier = verifier or Stage2Verifier()
        self.dispatcher = dispatcher or Dispatcher(config)
        self.incidents: List[Incident] = []
        self._master_key = bytes.fromhex(config.master_key_hex)

    # -- clip location convention: hub/clips/<node_id>_<counter>.wav ---------
    def clip_path(self, node_id: int, counter: int) -> str:
        return os.path.join(self.config.clips_dir, f"{node_id}_{counter}.wav")

    def _wait_for_clip(self, node_id: int, counter: int) -> Optional[str]:
        path = self.clip_path(node_id, counter)
        deadline = time.time() + self.config.clip_wait_s
        while time.time() < deadline:
            if os.path.exists(path) and os.path.getsize(path) > 1000:
                return path
            time.sleep(0.25)
        return None

    def process_packet(self, packet: bytes) -> Optional[Incident]:
        """Full chain for one sealed LoRa packet. Returns the Incident record
        (dispatched or not), or None if the packet was rejected outright."""
        # 1) authenticate + decrypt + replay-check
        try:
            probe = unseal(self._master_key, packet)           # id needed first
            node = self.registry.get(probe.node_id)
            last = node.last_counter if node else None
            alert = unseal(self._master_key, packet, last_counter=last)
        except PacketError as exc:
            log.warning("packet rejected: %s", exc)
            return None
        if node is None:
            log.warning("unknown node_id %d — ignoring", alert.node_id)
            return None
        self.registry.bump_counter(alert.node_id, alert.counter)
        log.info("ALERT node=%d(%s) event=%s conf=%.2f pir=%s light=%d",
                 alert.node_id, node.name, alert.event_name, alert.confidence,
                 alert.pir, alert.light)

        # 2) Stage-2 audio verification (clip arrives over WiFi/ESP-NOW)
        clip = self._wait_for_clip(alert.node_id, alert.counter)
        if clip is not None:
            audio_score = self.verifier.verify_wav(clip)
            log.info("stage-2 audio score %.2f (%s)", audio_score,
                     type(self.verifier.backend).name)
        else:
            # No clip: fall back to stage-1 confidence at a haircut. Multi-node
            # corroboration would slot in here (future work).
            audio_score = alert.confidence * 0.6
            log.warning("no clip within %.0fs — degraded score %.2f",
                        self.config.clip_wait_s, audio_score)

        # 3) evidence fusion → severity
        sev = fuse(alert, audio_score)
        log.info("severity %.2f [%s] (%s)", sev.score, sev.priority, sev.reasons)

        # 4) dispatch decision
        dispatched = False
        mission_id = None
        if audio_score >= self.config.verify_threshold and \
                sev.score >= self.config.dispatch_threshold:
            mission_id = self.dispatcher.dispatch(node.lat, node.lon,
                                                  sev.priority, node.name)
            dispatched = mission_id is not None
        else:
            log.info("below threshold — logged, no dispatch "
                     "(audio %.2f/%.2f, severity %.2f/%.2f)",
                     audio_score, self.config.verify_threshold,
                     sev.score, self.config.dispatch_threshold)

        inc = Incident(alert=alert, node_name=node.name, lat=node.lat,
                       lon=node.lon, audio_score=audio_score,
                       severity=sev.score, priority=sev.priority,
                       dispatched=dispatched, mission_id=mission_id,
                       reasons=sev.reasons)
        self.incidents.append(inc)
        return inc

    def process_node_alert(self, node_name, lat, lon, event, conf,
                           pir=False, light=128, dispatcher=None):
        """Handle an alert from a node that already ran Stage-1 on-device -- a
        real LoRa node, or the Wokwi/hardware sim reporting over WiFi. There is
        no clip, so the node's own confidence stands in for the audio score,
        then fusion + dispatch proceed as usual. This is the endpoint the
        simulated ESP32 hits, so the hardware demo drives the real dashboard."""
        from .packets import Alert
        audio_score = float(conf)
        alert = Alert(node_id=0, counter=0, event=int(event), confidence=float(conf),
                      pir=bool(pir), light=int(light), battery_pct=100)
        sev = fuse(alert, audio_score)
        disp = dispatcher or self.dispatcher
        dispatched = False
        mission_id = None
        if audio_score >= self.config.verify_threshold and \
                sev.score >= self.config.dispatch_threshold:
            mission_id = disp.dispatch(lat, lon, sev.priority, node_name)
            dispatched = mission_id is not None
        inc = Incident(alert=alert, node_name=node_name, lat=lat, lon=lon,
                       audio_score=audio_score, severity=sev.score,
                       priority=sev.priority, dispatched=dispatched,
                       mission_id=mission_id, reasons=sev.reasons)
        self.incidents.append(inc)
        return inc

    def process_clip(self, lat, lon, clip_path, stage1_conf, event,
                     pir=False, light=128, node_name="phone", dispatcher=None,
                     audio_analysis=None, confirmation_reasons=None, timeline=None):
        """Run Stage-2 + fusion + dispatch on an already-captured clip.

        Used by the phone test path, where a smartphone plays the sensing node:
        Stage-1 has already classified the uploaded clip, so this picks up from
        verification. `dispatcher` overrides the default (e.g. the sim drone).
        """
        from .packets import Alert
        audio_score = self.verifier.verify_wav(clip_path)
        alert = Alert(node_id=0, counter=0, event=event, confidence=stage1_conf,
                      pir=pir, light=light, battery_pct=100)
        sev = fuse(alert, audio_score)
        disp = dispatcher or self.dispatcher
        dispatched = False
        mission_id = None
        if audio_score >= self.config.verify_threshold and \
                sev.score >= self.config.dispatch_threshold:
            mission_id = disp.dispatch(lat, lon, sev.priority, node_name)
            dispatched = mission_id is not None
        inc = Incident(alert=alert, node_name=node_name, lat=lat, lon=lon,
                       audio_score=audio_score, severity=sev.score,
                       priority=sev.priority, dispatched=dispatched,
                       mission_id=mission_id, reasons=sev.reasons,
                       audio_analysis=audio_analysis,
                       confirmation_reasons=confirmation_reasons or [],
                       timeline=timeline or [])
        self.incidents.append(inc)
        return inc
