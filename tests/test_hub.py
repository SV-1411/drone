"""Hub tests. Explicit energy backend is used only as a deterministic test double."""
from __future__ import annotations
import math, os, sys, wave
import numpy as np
import pytest
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)
from hub.config import HubConfig
from hub.fusion import fuse
from hub.node_registry import Node,NodeRegistry
from hub.packets import Alert,PacketError,seal,unseal
from hub.pipeline import AlertPipeline
from hub.verifier import EnergyHeuristicBackend,Stage2Verifier
MASTER=bytes.fromhex("000102030405060708090a0b0c0d0e0f")
def _alert(counter=1,conf=.9,pir=True,light=20): return Alert(node_id=1,counter=counter,event=1,confidence=conf,pir=pir,light=light,battery_pct=88)
def test_packet_roundtrip():
 a=_alert(); b=unseal(MASTER,seal(MASTER,a)); assert len(seal(MASTER,a))==25; assert (b.node_id,b.counter,b.event)==(1,1,1); assert abs(b.confidence-.9)<.01; assert b.pir and b.light==20 and b.battery_pct==88
def test_packet_tamper_rejected():
 p=bytearray(seal(MASTER,_alert())); p[10]^=255
 with pytest.raises(PacketError,match="MAC"): unseal(MASTER,bytes(p))
def test_packet_wrong_key_rejected():
 with pytest.raises(PacketError,match="MAC"): unseal(b"\x99"*16,seal(MASTER,_alert()))
def test_packet_replay_rejected():
 p=seal(MASTER,_alert(counter=5)); unseal(MASTER,p,last_counter=4)
 with pytest.raises(PacketError,match="replayed"): unseal(MASTER,p,last_counter=5)
def test_packet_bad_length_and_magic():
 with pytest.raises(PacketError): unseal(MASTER,b"short")
 p=bytearray(seal(MASTER,_alert())); p[0]=ord("X")
 with pytest.raises(PacketError,match="magic"): unseal(MASTER,bytes(p))
def test_registry_roundtrip(tmp_path):
 path=str(tmp_path/"nodes.json"); r=NodeRegistry(path); r.add(Node(node_id=7,lat=28.61,lon=77.21,name="pole-7")); r.save(); n=NodeRegistry(path).get(7); assert n and n.name=="pole-7" and n.lat==28.61 and NodeRegistry(path).get(99) is None
def test_registry_counter_persists(tmp_path):
 path=str(tmp_path/"nodes.json"); r=NodeRegistry(path); r.add(Node(node_id=1,lat=0,lon=0)); r.bump_counter(1,41); assert NodeRegistry(path).get(1).last_counter==41; r.bump_counter(1,40); assert NodeRegistry(path).get(1).last_counter==41
def test_fusion_night_dark_pir_raises_severity(): assert fuse(_alert(pir=True,light=5),.5,23).score>fuse(_alert(pir=False,light=250),.5,12).score
def test_fusion_priority_escalates(): assert fuse(_alert(pir=True,light=5),.9,23).priority=="high" and fuse(_alert(pir=False,light=250,conf=.2),.2,12).priority=="normal"
def test_default_muffled_voice_recall_thresholds_are_75_percent():
 cfg=HubConfig()
 assert cfg.yamnet_single_strong_threshold == .75
 assert cfg.prosody_rescue_min_stage1_confidence == .75
def _write_wav(path,freq,amp,seconds=4,sr=16000):
 t=np.arange(int(sr*seconds))/sr; x=amp*np.sin(2*math.pi*freq*t); x[sr:sr+sr//2]*=3; x=np.clip(x,-1,1)
 with wave.open(path,"wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((x*32767).astype(np.int16).tobytes())
def test_energy_backend_orders_scream_above_silence(tmp_path):
 a=str(tmp_path/"loud.wav"); b=str(tmp_path/"quiet.wav"); _write_wav(a,1400,.5); _write_wav(b,200,.01); v=Stage2Verifier(backend=EnergyHeuristicBackend()); assert v.verify_wav(a)>v.verify_wav(b); assert v.verify_wav(a)>=.5
class _MockDispatcher:
 def __init__(self): self.calls=[]
 def dispatch(self,lat,lon,priority,node_name=""): self.calls.append((lat,lon,priority,node_name)); return "mission-test-1"
def _pipeline(tmp_path,clip_wait=.1):
 cfg=HubConfig(nodes_file=str(tmp_path/"nodes.json"),clips_dir=str(tmp_path/"clips"),clip_wait_s=clip_wait); os.makedirs(cfg.clips_dir,exist_ok=True); r=NodeRegistry(cfg.nodes_file); r.add(Node(node_id=1,lat=28.6178,lon=77.2137,name="pole-1")); r.save(); d=_MockDispatcher(); return AlertPipeline(cfg,r,verifier=Stage2Verifier(backend=EnergyHeuristicBackend()),dispatcher=d),d
def test_pipeline_dispatches_on_verified_scream(tmp_path):
 p,d=_pipeline(tmp_path); _write_wav(p.clip_path(1,1),1400,.5); i=p.process_packet(seal(MASTER,_alert(counter=1,pir=True,light=5))); assert i and i.dispatched and i.mission_id=="mission-test-1" and d.calls[0][0]==pytest.approx(28.6178)
def test_pipeline_no_dispatch_on_quiet_clip(tmp_path):
 p,d=_pipeline(tmp_path); _write_wav(p.clip_path(1,1),200,.01); i=p.process_packet(seal(MASTER,_alert(counter=1,conf=.3,pir=False,light=250))); assert i and not i.dispatched and d.calls==[]
def test_pipeline_rejects_unknown_node_and_replay(tmp_path):
 p,d=_pipeline(tmp_path); assert p.process_packet(seal(MASTER,Alert(node_id=42,counter=1,event=1,confidence=.9,pir=True,light=0,battery_pct=50))) is None; _write_wav(p.clip_path(1,3),1400,.5); a=_alert(counter=3); assert p.process_packet(seal(MASTER,a)) is not None and p.process_packet(seal(MASTER,a)) is None and len(d.calls)==1
def test_pipeline_no_dispatch_without_stage2_clip(tmp_path):
 p,d=_pipeline(tmp_path,clip_wait=.1); i=p.process_packet(seal(MASTER,_alert(counter=1,conf=.9))); assert i and i.audio_score==0 and not i.distress_confirmed and not i.dispatched and d.calls==[]
def test_stage2_temporal_gate_requires_multiple_positive_windows(tmp_path):
 class FakeBackend:
  name="fake-pann"
  def score(self,audio,sr=32000): return .9
 path=str(tmp_path/"clip.wav"); _write_wav(path,1400,.5); i=Stage2Verifier(backend=FakeBackend(),threshold=.7,min_positive_frames=3).verify_wav_detail(path); assert i.distress_confirmed and i.temporal_positive_frames>=3 and i.backend=="fake-pann"


def test_stage2_uses_yamnet_when_panns_is_unavailable(monkeypatch, tmp_path):
 class MissingPanns:
  def __init__(self, *args, **kwargs): raise RuntimeError("checkpoint unavailable")
 class FakeYamnet:
  name="YAMNet (AudioSet fallback)"
  def score(self,audio,sr=32000): return .60
 monkeypatch.setattr("hub.verifier.PannsBackend",MissingPanns)
 monkeypatch.setattr("hub.verifier.YamnetBackend",FakeYamnet)
 path=str(tmp_path/"clip.wav"); _write_wav(path,1400,.5)
 result=Stage2Verifier(threshold=.70,min_positive_frames=3,yamnet_threshold=.30,yamnet_min_positive_frames=3).verify_wav_detail(path)
 assert result.backend=="YAMNet (AudioSet fallback)"
 assert result.distress_confirmed and result.temporal_positive_frames>=3


def test_stage2_accepts_one_exceptionally_strong_yamnet_window(monkeypatch, tmp_path):
 class MissingPanns:
  def __init__(self,*a,**k): raise RuntimeError("PANN unavailable")
 class FakeYamnet:
  name="YAMNet (AudioSet fallback)"
  def score(self,audio,sr=32000): return .91
 monkeypatch.setattr("hub.verifier.PannsBackend",MissingPanns)
 monkeypatch.setattr("hub.verifier.YamnetBackend",FakeYamnet)
 path=str(tmp_path/"short-cry.wav"); _write_wav(path,400,.02,seconds=.3)
 result=Stage2Verifier(yamnet_threshold=.30,yamnet_min_positive_frames=3,yamnet_single_strong_threshold=.85).verify_wav_detail(path)
 assert result.distress_confirmed
 assert result.temporal_positive_frames == 1
 assert "one strong learned window" in result.reason


def test_stage2_does_not_accept_one_moderate_yamnet_window(monkeypatch, tmp_path):
 class MissingPanns:
  def __init__(self,*a,**k): raise RuntimeError("PANN unavailable")
 class FakeYamnet:
  name="YAMNet (AudioSet fallback)"
  def score(self,audio,sr=32000): return .60
 monkeypatch.setattr("hub.verifier.PannsBackend",MissingPanns)
 monkeypatch.setattr("hub.verifier.YamnetBackend",FakeYamnet)
 path=str(tmp_path/"short-moderate.wav"); _write_wav(path,400,.02,seconds=.3)
 result=Stage2Verifier(yamnet_threshold=.30,yamnet_min_positive_frames=3,yamnet_single_strong_threshold=.85).verify_wav_detail(path)
 assert not result.distress_confirmed
 assert result.temporal_positive_frames == 1


def _write_short_stressed_voice(path):
 sr=16000; x=np.zeros(sr*2,dtype=np.float32); n=int(.28*sr); start=int(.45*sr); t=np.arange(n,dtype=np.float32)/sr
 x[start:start+n]=.006*(np.sin(2*np.pi*230*t)+.35*np.sin(2*np.pi*460*t))
 x+=np.random.default_rng(7).normal(0,.0005,x.size).astype(np.float32)
 with wave.open(path,"wb") as w:
  w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((x*32767).astype(np.int16).tobytes())


def test_stage2_prosody_confirms_short_stressed_voice_and_enables_dispatch(tmp_path):
 class ZeroAudioSet:
  name="zero-audioset"
  def score(self,audio,sr=32000): return 0.0
 path=str(tmp_path/"stressed.wav"); _write_short_stressed_voice(path)
 verifier=Stage2Verifier(backend=ZeroAudioSet(),prosody_threshold=.55)
 assert not verifier.verify_wav_detail(path).distress_confirmed
 detail=verifier.verify_wav_detail(path,allow_spoken_stress=True)
 assert detail.distress_confirmed and detail.backend=="prosodic stressed-speech verifier"
 cfg=HubConfig(nodes_file=str(tmp_path/"nodes.json"),clips_dir=str(tmp_path/"clips"))
 reg=NodeRegistry(cfg.nodes_file); dispatcher=_MockDispatcher()
 pipe=AlertPipeline(cfg,reg,verifier=verifier,dispatcher=dispatcher)
 incident=pipe.process_clip(21.14,79.08,path,.65,event=2,pir=True,light=25,node_name="phone")
 assert incident.dispatched and dispatcher.calls


def test_high_confidence_cry_gets_prosody_rescue_when_yamnet_misses(tmp_path):
 class ZeroAudioSet:
  name="zero-audioset"
  def score(self,audio,sr=32000): return 0.0
 path=str(tmp_path/"muffled-cry.wav"); _write_short_stressed_voice(path)
 cfg=HubConfig(nodes_file=str(tmp_path/"nodes.json"),clips_dir=str(tmp_path/"clips"),prosody_rescue_min_stage1_confidence=.85)
 reg=NodeRegistry(cfg.nodes_file); dispatcher=_MockDispatcher()
 pipe=AlertPipeline(cfg,reg,verifier=Stage2Verifier(backend=ZeroAudioSet(),prosody_threshold=.55),dispatcher=dispatcher)
 incident=pipe.process_clip(21.14,79.08,path,.95,event=3,pir=True,light=25,node_name="muffled-phone")
 assert incident.distress_confirmed and incident.verifier_backend=="prosodic stressed-speech verifier"
 assert incident.dispatched and dispatcher.calls


def test_weak_generic_event_cannot_use_prosody_rescue(tmp_path):
 class ZeroAudioSet:
  name="zero-audioset"
  def score(self,audio,sr=32000): return 0.0
 path=str(tmp_path/"weak-vocal.wav"); _write_short_stressed_voice(path)
 cfg=HubConfig(nodes_file=str(tmp_path/"nodes.json"),clips_dir=str(tmp_path/"clips"),prosody_rescue_min_stage1_confidence=.85)
 reg=NodeRegistry(cfg.nodes_file); dispatcher=_MockDispatcher()
 pipe=AlertPipeline(cfg,reg,verifier=Stage2Verifier(backend=ZeroAudioSet(),prosody_threshold=.55),dispatcher=dispatcher)
 incident=pipe.process_clip(21.14,79.08,path,.60,event=3,pir=True,light=25,node_name="weak-phone")
 assert not incident.distress_confirmed
 assert not incident.dispatched and not dispatcher.calls
