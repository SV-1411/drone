"""Alert pipeline — Stage-1 sensing node -> Stage-2 PANN -> fusion -> dispatch."""
from __future__ import annotations
import logging, os, time
from dataclasses import dataclass, field
from typing import List, Optional
from .config import HubConfig
from .dispatcher import Dispatcher
from .fusion import fuse
from .node_registry import NodeRegistry
from .packets import Alert, PacketError, unseal
from .verifier import Stage2Verifier, VerificationResult
log=logging.getLogger("hub.pipeline")
@dataclass
class Incident:
    alert: Alert; node_name: str; lat: float; lon: float; audio_score: float; severity: float; priority: str; dispatched: bool; mission_id: Optional[str]; reasons: str
    audio_analysis: Optional[dict]=None; confirmation_reasons: list[str]=field(default_factory=list); timeline: list[dict]=field(default_factory=list); distress_confirmed: bool=False; acoustic_severity: float=0.0; verifier_backend: str="unknown"; verifier_detail: Optional[VerificationResult]=None; ts: float=field(default_factory=time.time)
class AlertPipeline:
    def __init__(self, config: HubConfig, registry: NodeRegistry, verifier: Optional[Stage2Verifier]=None, dispatcher: Optional[Dispatcher]=None):
        self.config=config; self.registry=registry
        self.verifier=verifier or Stage2Verifier(threshold=config.verify_threshold,min_positive_frames=config.min_positive_frames,checkpoint_path=config.pann_checkpoint_path,device=config.pann_device)
        self.dispatcher=dispatcher or Dispatcher(config); self.incidents: List[Incident]=[]; self._master_key=bytes.fromhex(config.master_key_hex)
    def clip_path(self,node_id:int,counter:int)->str: return os.path.join(self.config.clips_dir,f"{node_id}_{counter}.wav")
    def _wait_for_clip(self,node_id:int,counter:int)->Optional[str]:
        path=self.clip_path(node_id,counter); deadline=time.time()+self.config.clip_wait_s
        while time.time()<deadline:
            if os.path.exists(path) and os.path.getsize(path)>1000: return path
            time.sleep(.25)
        return None
    def _dispatch_allowed(self,detail:Optional[VerificationResult],severity:float)->bool:
        return detail is not None and detail.distress_confirmed and severity>=self.config.dispatch_threshold
    def _make_incident(self,alert,node,audio_score,sev,dispatched,mission_id,detail):
        return Incident(alert=alert,node_name=node.name,lat=node.lat,lon=node.lon,audio_score=audio_score,severity=sev.score,priority=sev.priority,dispatched=dispatched,mission_id=mission_id,reasons=sev.reasons,distress_confirmed=bool(detail.distress_confirmed) if detail else False,acoustic_severity=float(detail.acoustic_severity) if detail else 0.0,verifier_backend=detail.backend if detail else "unverified",verifier_detail=detail)
    def process_packet(self,packet:bytes)->Optional[Incident]:
        try:
            probe=unseal(self._master_key,packet); node=self.registry.get(probe.node_id); last=node.last_counter if node else None; alert=unseal(self._master_key,packet,last_counter=last)
        except PacketError as exc: log.warning("packet rejected: %s",exc); return None
        if node is None: log.warning("unknown node_id %d — ignoring",alert.node_id); return None
        self.registry.bump_counter(alert.node_id,alert.counter); clip=self._wait_for_clip(alert.node_id,alert.counter); detail=None
        if clip is not None:
            detail=self.verifier.verify_wav_detail(clip); audio_score=detail.classifier_probability if detail.distress_confirmed else 0.0
            log.info("stage-2 backend=%s confirmed=%s score=%.2f temporal=%d/%d",detail.backend,detail.distress_confirmed,detail.classifier_probability,detail.temporal_positive_frames,detail.temporal_frames)
        else:
            audio_score=0.0; log.warning("no Stage-1 audio clip within %.0fs — Stage-2 confirmation unavailable; no dispatch",self.config.clip_wait_s)
        sev=fuse(alert,audio_score); dispatched=False; mission_id=None
        if self._dispatch_allowed(detail,sev.score): mission_id=self.dispatcher.dispatch(node.lat,node.lon,sev.priority,node.name); dispatched=mission_id is not None
        inc=self._make_incident(alert,node,audio_score,sev,dispatched,mission_id,detail); self.incidents.append(inc); return inc
    def process_node_alert(self,node_name,lat,lon,event,conf,pir=False,light=128,dispatcher=None):
        from .packets import Alert
        alert=Alert(node_id=0,counter=0,event=int(event),confidence=float(conf),pir=bool(pir),light=int(light),battery_pct=100); sev=fuse(alert,0.0)
        inc=Incident(alert=alert,node_name=node_name,lat=lat,lon=lon,audio_score=0.0,severity=sev.score,priority=sev.priority,dispatched=False,mission_id=None,reasons=sev.reasons,distress_confirmed=False,acoustic_severity=0.0,verifier_backend="stage1-awaiting-pann")
        self.incidents.append(inc); return inc
    def process_clip(self,lat,lon,clip_path,stage1_conf,event,pir=False,light=128,node_name="phone",dispatcher=None,audio_analysis=None,confirmation_reasons=None,timeline=None):
        from .packets import Alert
        detail=self.verifier.verify_wav_detail(clip_path); audio_score=detail.classifier_probability if detail.distress_confirmed else 0.0; alert=Alert(node_id=0,counter=0,event=event,confidence=stage1_conf,pir=pir,light=light,battery_pct=100); sev=fuse(alert,audio_score); disp=dispatcher or self.dispatcher; dispatched=False; mission_id=None
        if self._dispatch_allowed(detail,sev.score): mission_id=disp.dispatch(lat,lon,sev.priority,node_name); dispatched=mission_id is not None
        inc=Incident(alert=alert,node_name=node_name,lat=lat,lon=lon,audio_score=audio_score,severity=sev.score,priority=sev.priority,dispatched=dispatched,mission_id=mission_id,reasons=sev.reasons,audio_analysis=audio_analysis,confirmation_reasons=confirmation_reasons or [],timeline=timeline or [],distress_confirmed=detail.distress_confirmed,acoustic_severity=detail.acoustic_severity,verifier_backend=detail.backend,verifier_detail=detail); self.incidents.append(inc); return inc
