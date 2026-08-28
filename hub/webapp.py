"""Hub web app: clip receiver, police dashboard, and the phone test mode.

Phone test mode lets you exercise the whole pipeline with just a phone and a
browser, no ESP32, no LoRa, no drone:

    /            police dashboard (live map, alerts, animated sim drone)
    /node        phone "sensing node" page (mic capture / simulate distress)
    POST /phone-alert   a phone uploads a WAV clip; the hub runs Stage-1 +
                        Stage-2 + fusion and dispatches the simulated drone
    /drone_state monitoring feed for the animated drone

This proves the detection-to-response pipeline works on real audio before any
hardware exists. It does NOT test LoRa range, the ESP32, real mic hardware, or
physical flight; those remain the hardware phases.
"""
from __future__ import annotations

import io
import logging
import os
import wave

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from .config import CONFIG
from .audio_analysis import AudioAnalysisSession
from .scream_dsp import scream_score
from .sim_drone import DroneFleet, FleetDispatcher, PhoneDrone
from .ui import brutalist_html

log = logging.getLogger("hub.web")

app = FastAPI(title="VanniKawachh hub")

# Two ways to visualise the response:
#  fleet       several auto-animated drones at prime stations; the nearest one
#              to each incident is dispatched (single-phone test, no hardware)
#  phone_drone a second phone reporting its real GPS as it moves (multi-phone)
fleet = DroneFleet(CONFIG.drone_bases, CONFIG.drone_speed_ms)
sim_dispatcher = FleetDispatcher(fleet)
phone_drone = PhoneDrone()


@app.on_event("startup")
def _init_pipeline():
    """When a cloud host runs `uvicorn hub.webapp:app` directly (no launcher),
    attach a default pipeline so the phone pages work out of the box."""
    if getattr(app.state, "pipeline", None) is None:
        from .node_registry import NodeRegistry
        from .pipeline import AlertPipeline
        app.state.pipeline = AlertPipeline(CONFIG, NodeRegistry(CONFIG.nodes_file))
        log.info("attached default pipeline for standalone/cloud serving")

CLASSES = ["background", "scream", "cry", "help"]
EVENT_CODE = {1: 1, 2: 3, 3: 2}          # class index -> firmware event code

# Stage-1 gate for the phone/browser path. A clip must be classified as a
# distress CLASS by the model AND be at least this confident AND this loud to
# count -- loudness alone is not distress. Raise these to be stricter.
CONFIG_MIN_CONF = float(os.environ.get("STAGE1_MIN_CONF", "0.70"))
CONFIG_MIN_LOUD = float(os.environ.get("STAGE1_MIN_LOUD", "0.45"))
# Real-mic scream detector (hub/scream_dsp.py) trigger level. This is what makes
# a genuine scream from a phone mic fire, since the bootstrap model can't.
SCREAM_THRESH = float(os.environ.get("SCREAM_THRESH", "0.40"))
# YAMNet (real AudioSet model) decision levels -- used when the model + a TFLite
# runtime are installed; otherwise the DSP detector above is the decider.
YAMNET_THRESH = float(os.environ.get("YAMNET_THRESH", "0.30"))
YAMNET_RMS_FLOOR = float(os.environ.get("YAMNET_RMS_FLOOR", "0.03"))
# AudioSet class name -> (webapp label, firmware event code)
_YAMNET_EVENT = {"crying": ("cry", 3), "whimper": ("cry", 3), "wail": ("cry", 3)}
_stage1_model = None
_phone_counter = 0


def _stage1():
    """Load the trained Stage-1 model once (None if not available)."""
    global _stage1_model
    if _stage1_model is None:
        try:
            from ml.infer_nn import Stage1NN, available
            _stage1_model = Stage1NN() if available() else False
        except Exception as exc:
            log.warning("Stage-1 model unavailable (%s); using loudness gate", exc)
            _stage1_model = False
    return _stage1_model or None


def read_wav_16k(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    else:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != 16000 and len(x) > 1:
        idx = np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr)).astype(np.int64)
        x = x[idx]
    return x


def stage1_phone(audio: np.ndarray):
    """Decide whether an uploaded clip is a distress event.

    The trained model is the ARBITER: the clip only counts as distress if the
    model classifies it as a distress class (scream / cry / help) with real
    confidence AND it is loud enough to be a genuine call for help. Loudness
    alone never triggers -- that was the old bug, where any loud sound (a door
    slam, a horn, a normal shout) counted as distress. A loudness floor is kept
    only to reject the model firing on quiet noise. Returns
    (triggered, label, confidence, event_code)."""
    # Preferred decider: YAMNet (hub/yamnet_detector.py), a real AudioSet model
    # with actual Screaming / Shout / Yell / Crying classes -- it recognises a
    # genuine distress vocalisation and ignores loud speech, horns and slams far
    # better than any heuristic. A small loudness floor stops it dispatching a
    # drone for a faint scream on a TV. Where YAMNet can't load (no TFLite
    # runtime, e.g. the free cloud tier), the DSP scream detector
    # (hub/scream_dsp.py) remains the decider: it scores the ACOUSTICS of a
    # scream (loud + high-pitched + voiced + sustained). The bootstrap-trained
    # model is NOT used for the live decision because it is unreliable on real
    # microphone audio -- it is kept for the standalone / firmware / eval paths.
    from .yamnet_detector import get_detector
    det = get_detector()
    if det is not None:
        rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
        sc, cls = det.distress_label(audio)
        if sc >= YAMNET_THRESH and rms >= YAMNET_RMS_FLOOR:
            label, event = next((v for k, v in _YAMNET_EVENT.items()
                                 if k in cls.lower()), ("scream", 1))
            log.info("YAMNet fired: %s %.2f (rms %.3f)", cls, sc, rms)
            return True, label, round(sc, 2), event
        return False, "background", round(sc, 2), 0
    sc = scream_score(audio)
    if sc >= SCREAM_THRESH:
        return True, "scream", round(sc, 2), 1
    return False, "background", round(sc, 2), 0


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.post("/clip/{node_id}/{counter}")
@app.put("/clip/{node_id}/{counter}")
async def upload_clip(node_id: int, counter: int, request: Request):
    os.makedirs(CONFIG.clips_dir, exist_ok=True)
    body = await request.body()
    path = os.path.join(CONFIG.clips_dir, f"{node_id}_{counter}.wav")
    with open(path, "wb") as f:
        f.write(body)
    return {"ok": True, "bytes": len(body)}


@app.post("/phone-alert")
async def phone_alert(request: Request, lat: float = None, lon: float = None,
                      pir: int = 1):
    """A phone (playing the sensing node) uploads a WAV clip. Runs the full
    pipeline and dispatches the simulated drone. Returns the decision."""
    global _phone_counter
    if lat is None or lon is None:
        lat, lon = CONFIG.test_lat, CONFIG.test_lon
    body = await request.body()
    os.makedirs(CONFIG.clips_dir, exist_ok=True)
    _phone_counter += 1
    path = os.path.join(CONFIG.clips_dir, f"phone_{_phone_counter}.wav")
    with open(path, "wb") as f:
        f.write(body)
    try:
        audio = read_wav_16k(body)
    except Exception as exc:
        return {"ok": False, "error": f"could not decode audio: {exc}"}

    analysis_session = AudioAnalysisSession()
    analysis_session.process_clip(audio, 16000)
    analysis = analysis_session.summary()
    latest = analysis["latest"] or {}
    triggered, label, conf, event = stage1_phone(audio)
    det_name = active_detector()["name"]
    if not triggered:
        return {"ok": True, "distress": False, "stage1": label,
                "confidence": round(conf, 2), "detector": det_name,
                "audio_analysis": analysis,
                "confirmation_reasons": [
                    "Audio classifier confidence did not reach the configured distress gate.",
                    f"Signal state: {latest.get('state', 'NORMAL_AUDIO')}."
                ]}

    pipeline = getattr(app.state, "pipeline", None)
    if pipeline is None:
        return {"ok": False, "error": "hub pipeline not attached"}
    eta = fleet.eta(lat, lon)                  # nearest drone's ETA before dispatch
    now = __import__("time").time()
    classifier_reason = f"{det_name} detected {label} at {conf:.0%}."
    peak_reason = (
        f"Sustained signal peak reached {latest.get('peak_duration_ms', 0) / 1000:.2f}s "
        f"(required {analysis['required_duration_ms'] / 1000:.2f}s)."
        if latest.get("state") == "PEAK_SUSTAINED"
        else f"Signal peak duration was {latest.get('peak_duration_ms', 0) / 1000:.2f}s; frequency evidence is supportive, not decisive."
    )
    reasons = [classifier_reason,
               f"RMS {latest.get('rms_amplitude', 0):.2f} vs baseline {latest.get('noise_floor', 0):.2f}.",
               f"Dominant frequency {latest.get('dominant_frequency_hz', 0):.0f} Hz; {peak_reason}",
               "Severity uses the existing Stage-2 fusion and environmental evidence."]
    timeline = [
        {"ts": now - max(0, len(audio) / 16000), "label": "Audio detected"},
        {"ts": now - 0.2, "label": f"{det_name} → {label} {conf:.0%}"},
        {"ts": now - 0.1, "label": f"Frequency peak → {latest.get('dominant_frequency_hz', 0):.0f} Hz"},
        {"ts": now, "label": "Distress confirmed by classifier and fusion"},
    ]
    inc = pipeline.process_clip(lat, lon, path, conf, event, pir=bool(pir),
                                light=25, node_name="phone-node",
                                dispatcher=sim_dispatcher, audio_analysis=analysis,
                                confirmation_reasons=reasons, timeline=timeline)
    if inc.dispatched:
        # also hand the incident to a drone phone, if one is connected
        phone_drone.assign(lat, lon, inc.mission_id, "phone-node")
    log.info("PHONE alert %s conf=%.2f -> severity %.2f dispatched=%s drone=%s eta=%ss",
             label, conf, inc.severity, inc.dispatched, eta.get("drone"), eta["eta_reach_s"])
    return {"ok": True, "distress": True, "stage1": label, "detector": det_name,
            "confidence": round(conf, 2), "audio_score": round(inc.audio_score, 2),
            "severity": round(inc.severity, 2), "dispatched": inc.dispatched,
            "mission_id": inc.mission_id, "lat": lat, "lon": lon,
            "drone": eta.get("drone"),
            "distance_m": eta["distance_m"], "eta_reach_s": eta["eta_reach_s"],
            "eta_total_s": eta["eta_total_s"]}


@app.get("/demo-scream")
def demo_scream():
    """A real human scream recording (public domain, 16 kHz WAV) for the /node
    page's SIMULATE DISTRESS button -- real audio through the real pipeline,
    accepted by both the YAMNet and DSP detectors (a synthetic tone is
    correctly rejected as a siren by YAMNet, so it can't be the demo signal)."""
    from fastapi.responses import FileResponse
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "models", "demo_scream.wav")
    return FileResponse(path, media_type="audio/wav")


@app.get("/drone_state")
def drone_state():
    # prefer a live drone phone; fall back to the fleet's currently active drone
    return phone_drone.snapshot() if phone_drone.fresh() else fleet.active()


@app.get("/drones")
def drones():
    """Every drone in the fleet with its station name and live position, so the
    dashboard can show where each one is (e.g. 'at GHRCE')."""
    return fleet.snapshots()


def active_detector() -> dict:
    """Which real-audio detector is deciding right now: YAMNet (the AudioSet
    model) if its TFLite runtime + model loaded, else the DSP acoustic fallback."""
    try:
        from .yamnet_detector import get_detector
        d = get_detector()
        if d is not None:
            return {"name": "YAMNet (AudioSet)", "backend": "yamnet",
                    "classes": [d._names[i] for i in d._distress_idx]}
    except Exception:
        pass
    return {"name": "DSP acoustic detector", "backend": "dsp",
            "classes": ["loud + high-pitch + voiced + sustained"]}


@app.get("/detector")
def detector():
    """Report the live scream/shout/cry detector so the UI can show which one is
    actually running (YAMNet vs the DSP fallback)."""
    d = active_detector()
    d["keywords"] = "browser speech recognition (help / bachao / madad)"
    return d


@app.get("/node-alert")
@app.post("/node-alert")
async def node_alert(node: str = "HW-NODE", lat: float = None, lon: float = None,
                     event: int = 1, conf: float = 0.9, pir: int = 1, light: int = 30):
    """A hardware / Wokwi sensing node that already ran Stage-1 on-device reports
    its alert here (this is the LoRa uplink). The hub fuses + dispatches the
    nearest drone and logs it on the dashboard -- so a simulated ESP32 drives the
    real deployed system end to end."""
    if lat is None or lon is None:
        lat, lon = CONFIG.test_lat, CONFIG.test_lon
    pipeline = getattr(app.state, "pipeline", None)
    if pipeline is None:
        return {"ok": False, "error": "hub pipeline not attached"}
    eta = fleet.eta(lat, lon)
    inc = pipeline.process_node_alert(node, lat, lon, event, conf, pir=bool(pir),
                                      light=light, dispatcher=sim_dispatcher)
    if inc.dispatched:
        phone_drone.assign(lat, lon, inc.mission_id, node)
    log.info("NODE-ALERT %s event=%s conf=%.2f -> severity %.2f dispatched=%s drone=%s",
             node, inc.alert.event_name, conf, inc.severity, inc.dispatched, eta.get("drone"))
    return {"ok": True, "distress": True, "node": node,
            "event": inc.alert.event_name, "confidence": round(float(conf), 2),
            "audio_score": round(inc.audio_score, 2), "severity": round(inc.severity, 2),
            "dispatched": inc.dispatched, "mission_id": inc.mission_id,
            "drone": eta.get("drone"), "lat": lat, "lon": lon,
            "distance_m": eta["distance_m"], "eta_reach_s": eta["eta_reach_s"]}


@app.get("/drone-mission")
def drone_mission():
    """A drone phone polls this to learn where to go."""
    return phone_drone.mission()


@app.post("/drone-report")
def drone_report(lat: float, lon: float, state: str = None, kit: int = None):
    """A drone phone reports its GPS (and optional state / kit-drop)."""
    phone_drone.report(lat, lon, state=state, kit=None if kit is None else bool(kit))
    return {"ok": True}


@app.get("/incidents")
def incidents():
    pipe = getattr(app.state, "pipeline", None)
    if pipe is None:
        return []
    return [
        {"ts": i.ts, "node_id": i.alert.node_id, "node_name": i.node_name,
         "lat": i.lat, "lon": i.lon, "event": i.alert.event_name,
         "confidence": i.alert.confidence,
         "audio_score": i.audio_score, "severity": i.severity,
         "priority": i.priority, "dispatched": i.dispatched,
         "mission_id": i.mission_id, "audio_analysis": i.audio_analysis,
         "confirmation_reasons": i.confirmation_reasons, "timeline": i.timeline}
        for i in pipe.incidents
    ]


@app.get("/nodes")
def nodes():
    pipe = getattr(app.state, "pipeline", None)
    if pipe is None:
        return []
    reg = pipe.registry
    with reg._lock:
        return [{"node_id": n.node_id, "lat": n.lat, "lon": n.lon, "name": n.name}
                for n in reg._nodes.values()]


# --------------------------------------------------------------------------
# Phone sensing-node page
# --------------------------------------------------------------------------
NODE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>VanniKawachh - Sensing Node (phone)</title>
<style>
 :root{--bg:#0a0a0a;--paper:#f4f4f0;--ink:#111;--line:#111;--mut:#666;--red:#b42318;--grn:#147a3d;--blu:#145b9e}
 *{box-sizing:border-box}
 body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;
      background:linear-gradient(180deg,#0b1220,#0d1627);color:var(--txt);
      padding:0 16px 30px;-webkit-tap-highlight-color:transparent}
 header{display:flex;align-items:center;gap:11px;padding:18px 2px 6px;overflow:hidden}
 .logo{width:38px;height:38px;border-radius:11px;display:flex;align-items:center;justify-content:center;
       background:linear-gradient(135deg,#6d5efc,#22c1c3);flex-shrink:0;
       box-shadow:0 0 20px rgba(109,94,252,.3)}
 .brand{font-weight:700;font-size:18px;white-space:nowrap} .badge{margin-left:auto;font-size:11px;font-weight:600;
       color:#34d399;background:#0f2a1c;border:1px solid #1c6b3f;padding:4px 10px;border-radius:20px;white-space:nowrap;flex-shrink:0}
 .tag{color:var(--mut);font-size:13px;margin:2px 2px 14px;overflow:hidden;white-space:nowrap}
 .tag-inner{display:inline-block;animation:marquee 20s linear infinite}
 @keyframes marquee{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
 .card{background:rgba(17,26,46,.7);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
       border:1px solid rgba(35,49,80,.6);border-radius:16px;padding:16px;
       margin:12px 0;box-shadow:0 8px 32px rgba(0,0,0,.35)}
 .lbl{font-size:11px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.7px;margin-bottom:9px}
 .row{display:flex;gap:8px;align-items:stretch}
 input{flex:1;min-width:0;padding:13px;border-radius:11px;border:1px solid var(--line);
       background:rgba(10,17,32,.8);color:var(--txt);font-size:15px;transition:border-color .2s,box-shadow .2s}
 input:focus{outline:none;border-color:var(--blu);box-shadow:0 0 0 3px rgba(59,130,246,.15)}
 .btn{border:0;border-radius:13px;padding:15px;font-size:15px;font-weight:600;color:#fff;width:100%;transition:transform .1s,box-shadow .1s}
 .btn:active{transform:scale(.97)}
 .btn.sm{width:auto;white-space:nowrap;padding:13px 16px;flex-shrink:0}
 .ghost{background:#152238;border:1px solid var(--line);color:var(--txt)}
 .loc{margin-top:11px;font-size:13px;line-height:1.4} .loc b{color:#7cc4ff}
 .shout{background:linear-gradient(135deg,#ef4444,#dc2626,#b91c1c);height:120px;font-size:21px;margin-top:6px;
        box-shadow:0 10px 30px rgba(239,68,68,.4),inset 0 1px 0 rgba(255,255,255,.1);
        transition:transform .15s,box-shadow .15s;position:relative;overflow:hidden}
 .shout::after{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;
        background:linear-gradient(45deg,transparent 30%,rgba(255,255,255,.08) 50%,transparent 70%);
        animation:shimmer 3s infinite}
 @keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
 .shout:active{transform:scale(.98);box-shadow:0 4px 12px rgba(239,68,68,.25)}
 .mic{background:linear-gradient(180deg,#3b82f6,#2563eb);box-shadow:0 6px 20px rgba(59,130,246,.3)}
 .mic.on{background:linear-gradient(180deg,#22c55e,#16a34a);box-shadow:0 6px 20px rgba(34,197,94,.3)}
 .mic:active{transform:scale(.98)}
 .meter{height:6px;background:#0a1120;border-radius:4px;overflow:hidden;margin-top:11px}
 .meter>div{height:100%;width:0;background:var(--grn);transition:width .1s}
 .v{font-size:16px;font-weight:700} .ok{color:var(--grn)} .no{color:var(--red)}
 .mut{color:var(--mut);font-size:12px;font-weight:400}
.a-section{margin:16px 0;padding:14px;background:rgba(13,21,37,.8);backdrop-filter:blur(8px);
          border:1px solid rgba(30,41,59,.6);border-radius:14px}
.a-canvas{width:100%;height:80px;border-radius:10px;background:#0a1120;display:block;margin-bottom:8px;border:1px solid #1a2640;transition:border-color .3s}
.a-canvas.sm{height:56px}
.a-row{display:flex;gap:8px;margin-bottom:8px}
.a-stat{flex:1;background:rgba(10,17,32,.6);border:1px solid rgba(35,49,80,.5);border-radius:10px;padding:10px;text-align:center;
       transition:border-color .3s,box-shadow .3s}
 .a-stat:hover{border-color:rgba(59,130,246,.3);box-shadow:0 0 12px rgba(59,130,246,.08)}
.a-stat .al{font-size:10px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.5px}
.a-stat .av{font-size:20px;font-weight:800;color:var(--txt);margin-top:2px}
.a-stat .au{font-size:10px;color:var(--mut)}
.a-state{padding:10px 14px;border-radius:10px;font-size:13px;font-weight:600;text-align:center;margin-bottom:10px;border:1px solid var(--line);transition:all .3s}
.a-state.idle{color:var(--mut);background:#0a1120}
.a-state.listening{color:#7cc4ff;background:#0f1f38;border-color:#274a75;box-shadow:0 0 12px rgba(59,130,246,.15)}
.a-state.calibrating{color:#f5b14c;background:#1a1508;border-color:#5a4a1a}
.a-state.potential-distress{color:#f5b14c;background:#1a1508;border-color:#5a4a1a;box-shadow:0 0 12px rgba(245,158,11,.15)}
.a-state.peak-sustained{color:#ef4444;background:#221018;border-color:#7f1d1d;box-shadow:0 0 16px rgba(239,68,68,.2)}
.a-state.confirmed{color:#22c55e;background:#0f2a1c;border-color:#1c6b3f;box-shadow:0 0 12px rgba(34,197,94,.15)}
.a-bar{height:8px;background:#1a2236;border-radius:4px;overflow:hidden;margin-top:8px}
.a-bar>div{height:100%;background:linear-gradient(90deg,var(--blu),#60a5fa);border-radius:4px;transition:width .15s ease-out}
.a-peak-bar>div{background:linear-gradient(90deg,#f59e0b,#ef4444)}
.a-explain{font-size:11px;color:var(--mut);line-height:1.5;margin-top:6px}
.a-explain b{color:var(--txt)}
</style></head><body>
<header>
 <div class="logo"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#fff"
   stroke-width="2.2" stroke-linecap="round"><path d="M4 12h0M8 8v8M12 4v16M16 8v8M20 12h0"/></svg></div>
 <div class="brand">VanniKawachh</div>
 <div class="badge">&#9679; NODE ONLINE</div>
</header>
<div class="tag"><span class="tag-inner">Acoustic distress sensing node &nbsp;&bull;&nbsp; Real-time acoustic detection &nbsp;&bull;&nbsp; AI-powered distress classification &nbsp;&bull;&nbsp; Autonomous drone response &nbsp;&bull;&nbsp; Acoustic distress sensing node &nbsp;&bull;&nbsp; Real-time acoustic detection &nbsp;&bull;&nbsp; AI-powered distress classification &nbsp;&bull;&nbsp; Autonomous drone response</span></div>

<div class="card">
 <div class="lbl">Incident location</div>
 <div class="row">
   <input id="addr" placeholder="Type an address or place name">
   <button class="btn sm ghost" id="search">Search</button>
 </div>
 <button class="btn ghost" id="useloc" style="margin-top:8px">&#128205; Use my current location</button>
 <div class="loc" id="loc">Default test area</div>
 <input type="hidden" id="lat"><input type="hidden" id="lon">
</div>

<button class="btn shout" id="shout">&#128266; SIMULATE DISTRESS
 <div class="mut" style="color:#ffdada;margin-top:4px">sends a scream signal &middot; works anywhere</div></button>
<button class="btn mic" id="mic">&#127908; Start listening (voice + screams)
 <div class="mut" style="color:#d5e6ff;margin-top:3px">detects "help/bachao" words + screams &middot; Chrome, https</div></button>
<div class="meter"><div id="meter"></div></div>

<div class="a-section" id="aSection" style="display:none">
 <div class="a-state idle" id="aState">&#9675; Microphone inactive</div>
 <div class="a-row">
  <div class="a-stat"><div class="al">Dominant Freq</div><div class="av" id="aFreq">&mdash;</div><div class="au">Hz</div></div>
  <div class="a-stat"><div class="al">RMS Level</div><div class="av" id="aRms">&mdash;</div><div class="au">amplitude</div></div>
  <div class="a-stat"><div class="al">Peak Energy</div><div class="av" id="aPeak">&mdash;</div><div class="au">magnitude</div></div>
 </div>
 <canvas id="cvWave" class="a-canvas" aria-label="Live audio waveform"></canvas>
 <div class="lbl" style="margin-bottom:4px">Waveform <span class="mut" style="font-weight:400;text-transform:none">&mdash; amplitude vs time</span></div>
 <canvas id="cvSpec" class="a-canvas" aria-label="Frequency spectrum"></canvas>
 <div class="lbl" style="margin-bottom:4px">Frequency Spectrum <span class="mut" style="font-weight:400;text-transform:none">&mdash; energy vs frequency</span></div>
 <canvas id="cvHist" class="a-canvas sm" aria-label="Frequency history"></canvas>
 <div class="lbl" style="margin-bottom:4px">Frequency History <span class="mut" style="font-weight:400;text-transform:none">&mdash; dominant freq over time</span></div>
 <div id="aPeakInfo" style="display:none">
  <div class="lbl" style="margin-bottom:4px">Peak Duration</div>
  <div class="a-bar a-peak-bar"><div id="aPeakBar" style="width:0"></div></div>
  <div style="display:flex;justify-content:space-between;margin-top:4px">
   <span class="mut" id="aPeakDur">0.00 / 2.00 s</span>
   <span class="mut" id="aPeakPct">0%</span>
  </div>
 </div>
 <div class="a-explain" id="aExplain"></div>
</div>

<div class="card">
 <div class="lbl">Status</div>
 <div class="v" id="res">Ready. Set a location, then trigger distress.</div>
 <div class="mut" id="res2"></div>
 <div class="mut" id="kw" style="margin-top:6px;color:#7cc4ff"></div>
 <div class="mut" id="det" style="margin-top:8px;font-weight:600"></div>
</div>

<script>
let lat = %TEST_LAT%, lon = %TEST_LON%, micOn = false, ctx, proc, buf = [], sr = 16000;
const $ = id => document.getElementById(id);
function coords(){ lat = parseFloat($('lat').value)||lat; lon = parseFloat($('lon').value)||lon; }
function setLoc(text){ $('lat').value = lat; $('lon').value = lon;
  $('loc').innerHTML = text + '<br><span class="mut">' + lat.toFixed(5) + ', ' + lon.toFixed(5) + '</span>'; }
setLoc('Default test area'); coords(); $('lat').value = lat; $('lon').value = lon;
// show which real-audio detector is live (YAMNet vs DSP fallback)
fetch('/detector').then(r=>r.json()).then(d=>{
  const yam = d.backend==='yamnet';
  $('det').innerHTML = (yam?'&#9989; ':'&#9881;&#65039; ') + 'Detector: <b style="color:'
    + (yam?'#34d399':'#f5b14c') + '">' + d.name + '</b>'
    + (d.classes? '<br><span class="mut">classes: '+d.classes.slice(0,6).join(', ')+'</span>':'');
}).catch(()=>{});
async function geocode(q){
  const u = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + encodeURIComponent(q);
  try{ const a = await (await fetch(u, {headers:{'Accept-Language':'en'}})).json();
    return a.length ? {lat:+a[0].lat, lon:+a[0].lon, name:a[0].display_name} : null; }catch(e){ return null; } }
async function revgeo(la, lo){
  try{ const a = await (await fetch('https://nominatim.openstreetmap.org/reverse?format=json&lat='+la+'&lon='+lo)).json();
    return a.display_name; }catch(e){ return null; } }
$('search').onclick = async () => {
  const q = $('addr').value.trim(); if(!q) return;
  $('loc').textContent = 'Searching...';
  const r = await geocode(q);
  if(r){ lat = r.lat; lon = r.lon; setLoc('<b>' + r.name + '</b>'); }
  else $('loc').textContent = 'Address not found. Try a nearby landmark.';
};
$('addr').addEventListener('keydown', e => { if(e.key === 'Enter'){ e.preventDefault(); $('search').click(); } });
$('useloc').onclick = () => {
  if(!navigator.geolocation){ alert('Location is not available on this browser.'); return; }
  $('loc').textContent = 'Getting your location...';
  navigator.geolocation.getCurrentPosition(async p => {
    lat = p.coords.latitude; lon = p.coords.longitude;
    const name = await revgeo(lat, lon); setLoc(name ? '<b>' + name + '</b>' : '<b>Current location</b>');
  }, () => { $('loc').textContent = 'Location blocked. Type an address (live GPS needs https).'; },
     {enableHighAccuracy:true});
};

function wavBlob(samples, rate){
  const b = new ArrayBuffer(44 + samples.length*2), v = new DataView(b);
  const ws = (o,s) => { for(let i=0;i<s.length;i++) v.setUint8(o+i, s.charCodeAt(i)); };
  ws(0,'RIFF'); v.setUint32(4, 36+samples.length*2, true); ws(8,'WAVE'); ws(12,'fmt ');
  v.setUint32(16,16,true); v.setUint16(20,1,true); v.setUint16(22,1,true);
  v.setUint32(24,rate,true); v.setUint32(28,rate*2,true); v.setUint16(32,2,true);
  v.setUint16(34,16,true); ws(36,'data'); v.setUint32(40, samples.length*2, true);
  for(let i=0;i<samples.length;i++){ let s=Math.max(-1,Math.min(1,samples[i]));
    v.setInt16(44+i*2, s<0?s*0x8000:s*0x7FFF, true); }
  return new Blob([b], {type:'audio/wav'});
}
function synthScream(){
  // a proper shriek: 500-1000 Hz fundamental with 6 harmonics (energy well
  // above 1.5 kHz) + roughness, loud and sustained -- matches the real-mic
  // scream detector so SIMULATE DISTRESS triggers the same path a real scream does.
  const rate=16000, n=rate*2, a=new Float32Array(n); let ph=0;
  for(let i=0;i<n;i++){ const t=i/rate;
    const f0=750+250*Math.sin(2*Math.PI*4*t);
    ph += 2*Math.PI*f0/rate;
    let s=0; for(let k=1;k<=6;k++) s += (1/k)*Math.sin(k*ph);
    s = s/2.0 + 0.12*(Math.random()*2-1);
    a[i]=Math.max(-1,Math.min(1, 0.9*s)); }
  return a;
}
async function send(samples){
  coords();
  $('res').innerHTML = 'Sending distress signal...'; $('res2').textContent = '';
  try{
    const r = await fetch(`/phone-alert?lat=${lat}&lon=${lon}&pir=1`,
      {method:'POST', headers:{'Content-Type':'audio/wav'}, body: wavBlob(samples,16000)});
    show(await r.json());
  }catch(e){
    $('res').innerHTML = '<span class="no">Cannot reach the hub</span>';
    $('res2').textContent = 'Make sure the hub is running and this phone is on the same WiFi.';
  }
}
function fmtT(s){ s=Math.round(s); const m=Math.floor(s/60); return m>0? m+'m '+(s%60)+'s' : s+'s'; }
function show(j){
  const res=document.getElementById('res'), res2=document.getElementById('res2');
  if(!j.ok){ res.innerHTML='<span class="no">error</span>'; res2.textContent=j.error||''; return; }
  if(!j.distress){ res.innerHTML='No distress detected ('+j.stage1+')'; res2.textContent='confidence '+j.confidence; return; }
  if(j.dispatched){
    const km=(j.distance_m/1000).toFixed(2);
    res.innerHTML='<span class="ok">Distress confirmed &mdash; nearest drone dispatched</span>';
    res2.innerHTML = (j.detector? '<b style="color:#34d399">'+j.detector+'</b> detected <b>'+j.stage1+'</b> ('+j.confidence+') &middot; ':'')
      + (j.drone? 'from <b style="color:#7cc4ff">'+j.drone+'</b> &middot; ':'')
      + 'ETA <b style="color:#eaf0fb">'+fmtT(j.eta_reach_s)+'</b>'
      + ' &middot; kit on arrival (total '+fmtT(j.eta_total_s)+')<br>'
      + 'distance '+km+' km &middot; severity '+j.severity+' &middot; '+(j.mission_id||'');
  } else {
    res.innerHTML='<span class="no">Distress, not dispatched</span>';
    res2.textContent = 'severity '+j.severity;
  }
}
// SIMULATE DISTRESS sends a REAL scream recording through the full audio
// pipeline (the hub's YAMNet detector rejects the synthetic tone as a siren);
// the synthetic scream is only the fallback if the clip can't be fetched.
async function sendDemoScream(){
  coords();
  $('res').innerHTML = 'Sending distress signal...'; $('res2').textContent = '';
  try{
    const wav = await (await fetch('/demo-scream')).blob();
    // feed through analyser for visualization if mic is on
    if(analyser && analyser.context){
      try{
        const ac=analyser.context;
        const arr=await wav.arrayBuffer();
        const decoded=await ac.decodeAudioData(arr);
        const src=ac.createBufferSource();
        src.buffer=decoded;
        src.connect(analyser);
        src.start();
      }catch(e){}
    }
    const r = await fetch(`/phone-alert?lat=${lat}&lon=${lon}&pir=1`,
      {method:'POST', headers:{'Content-Type':'audio/wav'}, body: wav});
    show(await r.json());
  }catch(e){ send(synthScream()); }
}
document.getElementById('shout').onclick = () => { sendDemoScream(); };

// ---- live distress detection ----------------------------------------------
// Two independent detectors run off the mic:
//   1. WORDS  -> browser speech recognition matches a distress vocabulary
//      (help / bachao / madad / save me ...). "hello" and normal talk do NOT
//      match, so words are recognised properly, not by loudness.
//   2. SCREAMS -> loud wordless clips go to the server's strict scream detector.
// A cooldown stops repeat-firing, and the mic is NOT routed to the speakers
// (that caused a feedback howl that kept re-triggering).
let listening=false, lastFire=0, recog=null, muteNode=null, tick=0, maxLevel=0;
const KEYWORDS = /\b(help me|help|bachao|bachaao|bacha o|madad|save me|save us|somebody help|please help|rescue me)\b/i;
function cooledDown(){ return Date.now() - lastFire > 6000; }
function markFired(){ lastFire = Date.now(); }

async function sendKeyword(word){
  if(!cooledDown()) return;
  coords();
  $('res').innerHTML = 'Heard "<b>'+word+'</b>" &mdash; dispatching...'; $('res2').textContent='';
  try{
    const r = await fetch(`/node-alert?node=phone&lat=${lat}&lon=${lon}&event=2&conf=0.96&pir=1&light=30`,{method:'POST'});
    const j = await r.json(); if(j.dispatched) markFired(); show(j);
  }catch(e){ $('res').innerHTML='<span class="no">Cannot reach the hub</span>'; }
}

async function sendScream(samples){
  coords();
  $('res').innerHTML='Loud sound &mdash; checking if it is a scream...';
  try{
    const r = await fetch(`/phone-alert?lat=${lat}&lon=${lon}&pir=1`,
      {method:'POST', headers:{'Content-Type':'audio/wav'}, body: wavBlob(samples,16000)});
    const j = await r.json();
    if(j.distress && j.dispatched){ markFired(); show(j); }
    else { $('res').innerHTML='Listening... <span class="mut">(that was not a scream)</span>'; }
  }catch(e){ $('res').innerHTML='<span class="no">Cannot reach the hub</span>'; }
}

function startKeywords(){
  const SRc = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!SRc){ $('kw').textContent='word detection: unavailable (open in Chrome)'; return; }
  recog = new SRc(); recog.continuous=true; recog.interimResults=false; recog.lang='en-IN';
  recog.onstart  = () => { $('kw').textContent='word detection ON — say "help" or "bachao"'; };
  recog.onresult = ev => { for(let i=ev.resultIndex;i<ev.results.length;i++){
      const res=ev.results[i]; if(!res.isFinal) continue;      // only act on final words
      const t=res[0].transcript.toLowerCase().trim(); $('kw').textContent='heard: "'+t+'"';
      const m=t.match(KEYWORDS); if(m) sendKeyword(m[0]); } };
  recog.onerror  = e => { $('kw').textContent='word detection: '+(e.error||'error'); };
  recog.onend    = () => { if(listening){ try{ recog.start(); }catch(e){} } };
  try{ recog.start(); }catch(e){ $('kw').textContent='word detection: could not start'; }
}

// ---- audio analysis visualization ----------------------------------------
let analyser=null, freqHist=[], specData=null, timeData=null, animFrame=null;
const FFT_SIZE=1024, HIST_MAX=120, REQUIRED_MS=2000;
let peakStartMs=0, lastPeakMs=0, gapMs=180, aState='IDLE';

function setupAnalyser(audioCtx, stream){
  analyser=audioCtx.createAnalyser();
  analyser.fftSize=FFT_SIZE;
  analyser.smoothingTimeConstant=0.8;
  const src=audioCtx.createMediaStreamSource(stream);
  src.connect(analyser);
  freqHist=[];
  specData=new Uint8Array(analyser.frequencyBinCount);
  timeData=new Uint8Array(analyser.fftSize);
}

function findDominant(){
  if(!analyser||!specData) return {freq:0,mag:0,energy:0};
  analyser.getByteFrequencyData(specData);
  const nyquist=analyser.context.sampleRate/2;
  const binHz=nyquist/specData.length;
  let bestI=0,bestV=0,totE=0;
  for(let i=1;i<specData.length;i++){
    totE+=specData[i];
    if(specData[i]>bestV){bestV=specData[i];bestI=i;}
  }
  return {freq:Math.round(bestI*binHz), mag:bestV, energy:totE/specData.length};
}

function drawWaveform(){
  const cv=$('cvWave'); if(!cv||!analyser) return;
  const c=cv.getContext('2d');
  const W=cv.width=cv.clientWidth; const H=cv.height=cv.clientHeight;
  analyser.getByteTimeDomainData(timeData);
  c.fillStyle='#0a1120'; c.fillRect(0,0,W,H);
  c.strokeStyle='#3b82f6'; c.lineWidth=1.5;
  c.beginPath();
  const step=W/timeData.length;
  for(let i=0;i<timeData.length;i++){
    const v=timeData[i]/128.0; const y=v*H/2;
    i===0?c.moveTo(0,y):c.lineTo(i*step,y);
  }
  c.stroke();
}

function drawSpectrum(){
  const cv=$('cvSpec'); if(!cv||!analyser) return;
  const c=cv.getContext('2d');
  const W=cv.width=cv.clientWidth; const H=cv.height=cv.clientHeight;
  analyser.getByteFrequencyData(specData);
  c.fillStyle='#0a1120'; c.fillRect(0,0,W,H);
  const barW=Math.max(1,W/specData.length*2.5);
  const nyquist=analyser.context.sampleRate/2;
  const binHz=nyquist/specData.length;
  for(let i=0;i<specData.length;i++){
    const x=i*barW; if(x>W) break;
    const h=(specData[i]/255)*H*0.9;
    const freq=i*binHz;
    c.fillStyle=freq>=250&&freq<=3500?'#3b82f6':'#1a2a44';
    c.fillRect(x,H-h,barW-1,h);
  }
  // highlight dominant
  const d=findDominant();
  if(d.mag>20){
    const dx=(d.freq/binHz)*barW;
    c.fillStyle='#22c55e';
    c.fillRect(dx-2,0,4,H);
    c.font='bold 11px sans-serif'; c.fillStyle='#22c55e';
    c.fillText(d.freq+' Hz',Math.min(dx+6,W-50),14);
  }
}

function drawHistory(){
  const cv=$('cvHist'); if(!cv) return;
  const c=cv.getContext('2d');
  const W=cv.width=cv.clientWidth; const H=cv.height=cv.clientHeight;
  c.fillStyle='#0a1120'; c.fillRect(0,0,W,H);
  if(freqHist.length<2) return;
  const maxF=2000, minF=0;
  const step=W/(HIST_MAX-1);
  // threshold line
  const thr=500;
  const thrY=H-(thr-minF)/(maxF-minF)*H;
  c.strokeStyle='#5a4a1a'; c.lineWidth=1; c.setLineDash([4,4]);
  c.beginPath(); c.moveTo(0,thrY); c.lineTo(W,thrY); c.stroke();
  c.setLineDash([]);
  c.fillStyle='#5a4a1a'; c.font='9px sans-serif'; c.fillText('vocal range',4,thrY-3);
  // line
  c.strokeStyle='#3b82f6'; c.lineWidth=2;
  c.beginPath();
  const start=Math.max(0,freqHist.length-HIST_MAX);
  for(let i=start;i<freqHist.length;i++){
    const x=(i-start)*step;
    const y=H-(Math.min(freqHist[i],maxF)-minF)/(maxF-minF)*H;
    i===start?c.moveTo(x,y):c.lineTo(x,y);
  }
  c.stroke();
  // latest dot
  const last=freqHist[freqHist.length-1];
  const lx=(freqHist.length-1-start)*step;
  const ly=H-(Math.min(last,maxF)-minF)/(maxF-minF)*H;
  c.fillStyle=aState==='PEAK_SUSTAINED'?'#ef4444':aState==='POTENTIAL_DISTRESS'?'#f5b14c':'#3b82f6';
  c.beginPath(); c.arc(lx,ly,4,0,Math.PI*2); c.fill();
}

function updateASection(){
  const el=$('aSection'); if(!el) return;
  if(!micOn){el.style.display='none'; return;}
  el.style.display='';
  const d=findDominant();
  $('aFreq').textContent=d.freq||'—';
  $('aRms').textContent=d.mag?(d.mag/255).toFixed(2):'—';
  $('aPeak').textContent=d.mag?(d.mag/255).toFixed(2):'—';
  // state
  const now=Date.now();
  const isAbove=d.mag>40&&d.freq>=250&&d.freq<=3500;
  if(isAbove){
    if(!peakStartMs) peakStartMs=now;
    lastPeakMs=now;
    const dur=now-peakStartMs;
    if(dur>=REQUIRED_MS) aState='PEAK_SUSTAINED';
    else aState='POTENTIAL_DISTRESS';
  }else if(peakStartMs&&now-lastPeakMs>gapMs){
    peakStartMs=0; lastPeakMs=0; aState='LISTENING';
  }

  const stEl=$('aState');
  const labels={IDLE:'&#9675; Microphone inactive',LISTENING:'&#9679; Listening',CALIBRATING:'&#9679; Calibrating...',POTENTIAL_DISTRESS:'&#9888; Potential distress',PEAK_SUSTAINED:'&#9888; Sustained peak'};
  stEl.className='a-state '+aState.toLowerCase().replace('_','-');
  stEl.innerHTML=labels[aState]||aState;

  // peak bar
  const pi=$('aPeakInfo');
  if(aState==='POTENTIAL_DISTRESS'||aState==='PEAK_SUSTAINED'){
    pi.style.display='';
    const dur=(Date.now()-peakStartMs)/1000;
    const req=REQUIRED_MS/1000;
    const pct=Math.min(100,dur/req*100);
    $('aPeakBar').style.width=pct+'%';
    $('aPeakDur').textContent=dur.toFixed(2)+' / '+req.toFixed(2)+' s';
    $('aPeakPct').textContent=Math.round(pct)+'%';
  }else{pi.style.display='none';}

  // explanation
  const ex=$('aExplain');
  if(aState==='PEAK_SUSTAINED'){
    ex.innerHTML='<b>&#10003; SUSTAINED PEAK CONFIRMED</b><br>Peak duration met the required threshold. YAMNet classification and fusion determine final dispatch.';
  }else if(aState==='POTENTIAL_DISTRESS'){
    ex.innerHTML='Peak detected at <b>'+d.freq+' Hz</b>. Waiting for sustained duration...';
  }else{ex.innerHTML='';}
}

function drawLoop(){
  if(!micOn||!analyser) return;
  drawWaveform(); drawSpectrum(); drawHistory(); updateASection();
  animFrame=requestAnimationFrame(drawLoop);
}

function feedAnalyserFromSamples(samples){
  // feed decoded samples through the analyser for SIMULATE DISTRESS visualization
  if(!analyser||!analyser.context) return;
  const ac=analyser.context;
  const buf=ac.createBuffer(1,samples.length,16000);
  buf.getChannelData(0).set(samples);
  const src=ac.createBufferSource();
  src.buffer=buf;
  src.connect(analyser);
  // also connect to destination so it's audible if not muted
  // (muted via muteNode gain=0, but analyser still sees it)
  src.start();
}

document.getElementById('mic').onclick = async () => {
  if(micOn){
    micOn=false; listening=false;

    if(animFrame){cancelAnimationFrame(animFrame);animFrame=null;}

    analyser=null; freqHist=[]; peakStartMs=0; lastPeakMs=0; aState='IDLE';
    $('mic').classList.remove('on'); $('mic').innerHTML='&#127908; Start listening (voice + screams)';
    if(recog){ try{ recog.stop(); }catch(e){} recog=null; }
    if(ctx){ try{ ctx.close(); }catch(e){} }
    $('res').textContent='Stopped listening.'; $('kw').textContent=''; return;
  }
  try{
    const st = await navigator.mediaDevices.getUserMedia(
      {audio:{channelCount:1, echoCancellation:false, noiseSuppression:false, autoGainControl:false}});
    ctx = new AudioContext(); await ctx.resume(); sr = ctx.sampleRate; buf = []; maxLevel=0;
    setupAnalyser(ctx, st);

    const src = ctx.createMediaStreamSource(st);
    proc = ctx.createScriptProcessor(4096,1,1);
    muteNode = ctx.createGain(); muteNode.gain.value = 0;      // no playback -> no feedback
    proc.onaudioprocess = e => {
      const d = e.inputBuffer.getChannelData(0);
      let peak=0; for(let i=0;i<d.length;i++){ buf.push(d[i]); if(Math.abs(d[i])>peak) peak=Math.abs(d[i]); }
      if(peak>maxLevel) maxLevel=peak;
      $('meter').style.width = Math.min(100, peak*160) + '%';
      if((++tick & 3)===0 && cooledDown()) $('res2').textContent='listening... mic level '+Math.round(peak*100)+'%';
      if(buf.length >= sr*2){
        const win=buf.slice(0, sr*2); buf=[];
        let s=0; for(let i=0;i<win.length;i++) s+=win[i]*win[i];
        const rms=Math.sqrt(s/win.length);
        if(rms > 0.045 && cooledDown()){         // loud window -> ask the server
          const ratio=sr/16000, len=Math.floor(win.length/ratio), out=new Float32Array(len);
          for(let i=0;i<len;i++) out[i]=win[Math.floor(i*ratio)];
          sendScream(out);
        }
      }
    };
    src.connect(proc); proc.connect(muteNode); muteNode.connect(ctx.destination);
    listening=true; micOn=true;
    $('mic').classList.add('on'); $('mic').innerHTML='Listening... (tap to stop)';
    $('res').textContent='Listening for "help", "bachao", or a scream...';
    startKeywords();

    drawLoop();
  }catch(err){ alert('Mic needs permission + https. ' + err); }
};
</script></body></html>"""


@app.get("/node", response_class=HTMLResponse)
def node_page():
    return brutalist_html(
        NODE_HTML.replace("%TEST_LAT%", str(CONFIG.test_lat))
        .replace("%TEST_LON%", str(CONFIG.test_lon))
    )


DRONE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>VanniKawachh - Drone (phone)</title>
<style>
 :root{--bg:#0b1220;--card:#111a2e;--line:#233150;--txt:#eaf0fb;--mut:#8ea0bf;--grn:#22c55e;--blu:#3b82f6}
 *{box-sizing:border-box}
 body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;
      background:linear-gradient(180deg,#0b1220,#0d1627);color:var(--txt);padding:0 16px 30px}
 header{display:flex;align-items:center;gap:11px;padding:18px 2px 6px}
 .logo{width:38px;height:38px;border-radius:11px;display:flex;align-items:center;justify-content:center;
       background:linear-gradient(135deg,#22c1c3,#3b82f6)}
 .brand{font-weight:700;font-size:18px} .badge{margin-left:auto;font-size:11px;font-weight:600;
       color:#7cc4ff;background:#0f1f38;border:1px solid #274a75;padding:4px 10px;border-radius:20px}
 .tag{color:var(--mut);font-size:13px;margin:2px 2px 14px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;
       margin:12px 0;box-shadow:0 8px 26px rgba(0,0,0,.28)}
 .lbl{font-size:11px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.7px}
 .v{font-size:16px;font-weight:700;margin-top:3px} .big{font-size:34px;font-weight:800;margin:2px 0}
 .btn{font-size:15px;font-weight:600;border:0;border-radius:13px;padding:15px;width:100%;margin:6px 0;color:#fff}
 .mut{color:var(--mut);font-size:12px;font-weight:400}
 #gps{background:var(--blu)} #gps.on{background:var(--grn)} #step{background:#243352;border:1px solid var(--line)}
 #kit{background:linear-gradient(180deg,#f0a93a,#d98a1e);color:#1a1206} #rtl{background:#6d5efc}
</style></head><body>
<header>
 <div class="logo"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#fff"
   stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
   <circle cx="12" cy="12" r="3.2"/></svg></div>
 <div class="brand">VanniKawachh</div>
 <div class="badge">&#9679; DRONE UNIT</div>
</header>
<div class="tag">Autonomous response unit &middot; walk toward the incident and the dashboard tracks you</div>

<div class="card">
  <div class="lbl">Assigned incident</div>
  <div class="v" id="tgt">Waiting for an alert...</div>
  <div class="lbl" style="margin-top:12px">Distance to incident</div>
  <div class="big" id="dist">&mdash;</div>
  <div class="lbl">Status</div><div class="v" id="st">IDLE</div>
</div>

<button class="btn" id="gps">&#128225; Follow my GPS
 <div class="mut" style="color:#d5e6ff;margin-top:3px">real movement &middot; needs https</div></button>
<button class="btn" id="step">&#128694; STEP toward incident</button>
<button class="btn" id="kit">&#128230; DROP FIRST-AID KIT</button>
<button class="btn" id="rtl">&#8617; RETURN TO BASE</button>

<script>
let target=null, mid=null, me=null, watch=null, kit=false;
function hav(a,b){const R=6371000,r=x=>x*Math.PI/180;
  const dl=r(b[0]-a[0]),dn=r(b[1]-a[1]);
  const x=Math.sin(dl/2)**2+Math.cos(r(a[0]))*Math.cos(r(b[0]))*Math.sin(dn/2)**2;
  return 2*R*Math.asin(Math.sqrt(x));}
async function pollMission(){
 try{ const m=await (await fetch('/drone-mission')).json();
   if(m.has_mission){ target=m.target; mid=m.mission_id;
     document.getElementById('tgt').textContent=`${target[0].toFixed(5)}, ${target[1].toFixed(5)} (${mid})`;
     if(!me) me=[target[0]+0.005, target[1]]; // start at base if we have no position yet
   } }catch(e){}
 setTimeout(pollMission,1500);
}
function flash(msg){ document.getElementById('st').textContent = msg; }
async function report(state){
 if(!me){ if(target) me=[target[0]+0.005, target[1]]; else return; }
 let d = target? hav(me,target):null;
 let s = state || (d===null?'IDLE': d<20?'HOVERING':'ENROUTE');
 document.getElementById('st').textContent=s;
 document.getElementById('dist').textContent = d===null?'\\u2014':(d<1000?d.toFixed(0)+' m':(d/1000).toFixed(2)+' km');
 try{ await fetch(`/drone-report?lat=${me[0]}&lon=${me[1]}&state=${s}&kit=${kit?1:0}`,{method:'POST'}); }catch(e){}
}
document.getElementById('step').onclick=()=>{
  if(!target){ flash('No incident yet - trigger an alert on the sensor phone'); return; }
  if(!me) me=[target[0]+0.005,target[1]];
  me=[me[0]+(target[0]-me[0])*0.25, me[1]+(target[1]-me[1])*0.25]; report(); };
document.getElementById('kit').onclick=()=>{
  if(!target){ flash('No incident yet - trigger an alert first'); return; }
  kit=true; report('DELIVERING'); };
document.getElementById('rtl').onclick=()=>{
  if(!target){ flash('No incident yet'); return; }
  report('RTL'); };
document.getElementById('gps').onclick=()=>{
  const b=document.getElementById('gps');
  if(watch){ navigator.geolocation.clearWatch(watch); watch=null; b.classList.remove('on'); b.innerHTML='&#128225; Follow my GPS'; return; }
  if(!navigator.geolocation){ alert('No geolocation. Use STEP, or serve over https.'); return; }
  watch=navigator.geolocation.watchPosition(p=>{ me=[p.coords.latitude,p.coords.longitude]; report(); },
    e=>{ alert('GPS needs https on a phone. Use the STEP button on http.'); },
    {enableHighAccuracy:true, maximumAge:1000});
  b.classList.add('on'); b.innerHTML='&#128225; Following your GPS (tap to stop)';
};
pollMission(); setInterval(()=>report(), 2000);
</script></body></html>"""


@app.get("/drone-phone", response_class=HTMLResponse)
def drone_phone_page():
    return brutalist_html(DRONE_HTML)


# --------------------------------------------------------------------------
# Police dashboard (with the animated sim drone)
# --------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VanniKawachh - Police Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 *{box-sizing:border-box}
 html,body{margin:0;height:100%;font-family:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif}
 #app{display:flex;height:100vh}
 #panel{width:360px;overflow-y:auto;background:rgba(11,18,32,.92);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);color:#eaf0fb;padding:16px;border-right:1px solid rgba(35,49,80,.4)}
 #map{flex:1}
 .hd{display:flex;align-items:center;gap:10px;margin-bottom:4px}
 .logo{width:34px;height:34px;border-radius:10px;display:flex;align-items:center;justify-content:center;
       background:linear-gradient(135deg,#6d5efc,#22c1c3);box-shadow:0 0 16px rgba(109,94,252,.3);flex-shrink:0}
 .brand{font-weight:700;font-size:17px} .sub{color:#8ea0bf;font-size:12px;margin:0 0 12px 44px}
 #chip{display:inline-block;padding:5px 12px;border-radius:20px;font-size:12px;font-weight:600;
       background:rgba(17,26,46,.8);border:1px solid rgba(35,49,80,.6);margin-bottom:12px;
       backdrop-filter:blur(6px)}
 .inc{border:1px solid rgba(35,49,80,.6);border-radius:12px;padding:11px;margin-bottom:8px;
      background:rgba(17,26,46,.7);backdrop-filter:blur(8px);transition:border-color .3s,box-shadow .3s}
 .inc:hover{border-color:rgba(59,130,246,.3);box-shadow:0 0 12px rgba(59,130,246,.08)}
 .inc.d{border-color:#ef4444;background:rgba(34,16,24,.8);box-shadow:0 0 16px rgba(239,68,68,.1)}
 .inc .m{color:#8ea0bf;font-size:11px;margin-top:4px;line-height:1.4}
 .b{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700}
 .high{background:#ef4444;color:#fff} .normal{background:#f5b14c;color:#1a1206}
 .drone{font-size:24px;filter:drop-shadow(0 2px 4px rgba(0,0,0,.4))}
 .stlbl{background:#0b1220;color:#9fc3ff;border:1px solid #274a75;border-radius:6px;
        font-size:11px;font-weight:600;padding:1px 6px;box-shadow:none}
 .stlbl:before{display:none}
 #pipe{margin:2px 0 14px}
 .ptitle{font-size:11px;font-weight:700;color:#8ea0bf;text-transform:uppercase;letter-spacing:.7px;margin:0 0 7px}
 .pstep{display:flex;align-items:center;gap:9px;padding:8px 11px;margin:5px 0;border-radius:10px;
        background:rgba(14,23,48,.7);border:1px solid rgba(28,41,70,.6);color:#6b7ea3;font-size:12.5px;font-weight:600;
        transition:all .35s;position:relative}
 .pstep .pi{font-size:15px;filter:grayscale(1);opacity:.45;transition:all .35s}
 .pstep .pv{margin-left:auto;color:#7cc4ff;font-weight:700;font-size:12px}
 .pstep.on{background:rgba(18,35,63,.8);border-color:#3b82f6;color:#eaf0fb;box-shadow:0 0 16px rgba(59,130,246,.35)}
 .pstep.on .pi{filter:none;opacity:1;transform:scale(1.15)}
 .pstep.done{background:rgba(15,36,25,.8);border-color:#22c55e;color:#cfe9d6;box-shadow:0 0 8px rgba(34,197,94,.1)}
 .pstep.done .pi{filter:none;opacity:1}
 .pstep.fail{border-color:#ef4444;color:#f2b8b8}
 @media(max-width:720px){ #app{flex-direction:column} #panel{width:auto;height:42vh;order:2}
   #map{height:58vh;order:1} }
</style></head><body>
<div id="app">
 <div id="panel">
  <div class="hd">
   <div class="logo"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#fff"
     stroke-width="2.2" stroke-linecap="round"><path d="M4 12h0M8 8v8M12 4v16M16 8v8M20 12h0"/></svg></div>
   <div class="brand">VanniKawachh</div>
  </div>
  <div class="sub">Acoustic distress network &middot; live response</div>
  <div id="chip">Drone: idle</div>
  <div id="pipe">
    <div class="ptitle">Detection pipeline</div>
    <div id="detbadge" style="font-size:12px;font-weight:700;margin:-2px 0 8px"></div>
    <div class="pstep" id="ps0"><span class="pi">&#127908;</span> Node detects (Stage-1)<span class="pv" id="pv0"></span></div>
    <div class="pstep" id="ps1"><span class="pi">&#128225;</span> LoRa alert<span class="pv" id="pv1"></span></div>
    <div class="pstep" id="ps2"><span class="pi">&#129504;</span> Hub verifies (Stage-2)<span class="pv" id="pv2"></span></div>
    <div class="pstep" id="ps3"><span class="pi">&#9878;</span> Fusion<span class="pv" id="pv3"></span></div>
    <div class="pstep" id="ps4"><span class="pi">&#128641;</span> Dispatch nearest drone<span class="pv" id="pv4"></span></div>
  </div>
  <div id="list">No incidents yet. Open <b>/node</b> on a phone and trigger a distress signal.</div>
 </div>
 <div id="map"></div>
</div>
<script>
const map = L.map('map').setView([%TEST_LAT%, %TEST_LON%], 13);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap'}).addTo(map);
let seen=0, curMid=null, targetM=null, kitM=null;
const fleetM = {};   // station name -> {base, marker, path}
function beep(){ try{ const c=new (window.AudioContext||window.webkitAudioContext)();
  const o=c.createOscillator(), g=c.createGain(); o.connect(g); g.connect(c.destination);
  o.frequency.value=880; g.gain.value=.3; o.start();
  setTimeout(()=>o.frequency.value=660,200); setTimeout(()=>{o.stop();c.close()},800);}catch(e){} }
const droneIcon = L.divIcon({html:'<div class=drone>🚁</div>',className:'',iconSize:[26,26],iconAnchor:[13,13]});
function fmtT(s){ s=Math.round(s); return s>=60? Math.floor(s/60)+'m '+(s%60)+'s' : s+'s'; }
function fmtD(m){ return m<1000? Math.round(m)+' m' : (m/1000).toFixed(2)+' km'; }

// Draw every drone: a labelled station dot at its base, and a live 🚁 marker
// that sits ON the station when idle and moves along its flight when responding.
async function pollFleet(){
 try{
  const ds = await (await fetch('/drones')).json();
  ds.forEach(d=>{
    let f = fleetM[d.name];
    if(!f){
      const base = L.circleMarker(d.home,{radius:6,color:'#5ea9ff',fillColor:'#12305a',fillOpacity:.95})
        .addTo(map).bindTooltip(d.name,{permanent:true,direction:'top',offset:[0,-6],className:'stlbl'});
      const marker = L.marker([d.lat,d.lon],{icon:droneIcon}).addTo(map);
      f = fleetM[d.name] = {base, marker, path:null};
    }
    f.marker.setLatLng([d.lat,d.lon]);
    f.marker.bindTooltip('🚁 '+d.name+' · '+d.location_name+(d.available?'':' · '+d.state));
    if(!d.available && d.home){ const pts=[d.home,[d.lat,d.lon]];
      if(!f.path) f.path=L.polyline(pts,{color:'#e5484d',dashArray:'5,6'}).addTo(map); else f.path.setLatLngs(pts);
    } else if(f.path){ map.removeLayer(f.path); f.path=null; }
  });
  const idle = ds.filter(d=>d.available).length, act = ds.find(d=>!d.available);
  document.getElementById('chip').textContent = act
    ? act.name+' responding · '+(act.state||'').toLowerCase()
      + (act.eta_reach_s && ['TAKEOFF','ENROUTE'].includes(act.state)? ' · ETA '+fmtT(act.eta_reach_s):'')
    : idle+' / '+ds.length+' drones idle';
 }catch(e){}
 setTimeout(pollFleet, 500);
}

// Track the active mission for the incident pin, kit drop, and auto-framing.
async function pollDrone(){
 try{
  const d = await (await fetch('/drone_state')).json();
  if(d.mission_id && d.mission_id !== curMid){
    curMid = d.mission_id;
    if(kitM){ map.removeLayer(kitM); kitM=null; }
    if(d.target && d.lat!=null){ map.fitBounds([[d.lat,d.lon], d.target], {padding:[70,70], maxZoom:16}); }
    else if(d.target){ map.setView(d.target, 15); }
  }
  if(d.target){
    if(!targetM){ targetM=L.marker(d.target).addTo(map).bindPopup('incident'); }
    else targetM.setLatLng(d.target);
  }
  if(d.kit_dropped && d.target && !kitM){
    kitM=L.marker(d.target).addTo(map).bindPopup('📦 first-aid kit dropped').openPopup();
  }
 }catch(e){}
 setTimeout(pollDrone, 400);
}
function setStep(i,cls,val){ const s=document.getElementById('ps'+i);
  s.className='pstep '+cls; if(val!==undefined) document.getElementById('pv'+i).textContent=val; }
function resetPipe(){ for(let i=0;i<5;i++) setStep(i,''," "); }
// Light the 5 stages one by one as an alert flows through, showing each value.
function animatePipeline(inc){
  resetPipe();
  const conf = inc.confidence!=null ? Math.round(inc.confidence*100)+'%' : '';
  const steps = [
    [0, inc.event + (conf?' · '+conf:'')],
    [1, '433 MHz'],
    [2, 'audio ' + (inc.audio_score!=null?inc.audio_score:'')],
    [3, 'severity ' + (inc.severity!=null?inc.severity:'')],
    [4, inc.dispatched ? (inc.mission_id||'sent') : 'below threshold']
  ];
  steps.forEach(([idx,val],k)=>{
    setTimeout(()=>{
      if(k>0) setStep(steps[k-1][0],'done',steps[k-1][1]);
      const last = (k===steps.length-1);
      const cls = last ? (inc.dispatched?'done':'fail') : 'on';
      setStep(idx, cls, val);
    }, k*650);
  });
}
async function pollInc(){
 try{
  const inc = await (await fetch('/incidents')).json();
  if(inc.length!==seen){ const fresh=inc.slice(seen); seen=inc.length;
    fresh.forEach(i=>{ if(i.dispatched){ beep(); } });
    if(fresh.length) animatePipeline(fresh[fresh.length-1]);
    document.getElementById('list').innerHTML = inc.slice().reverse().map(i=>`
     <div class="inc ${i.dispatched?'d':''}">
       <b>${i.event}</b> <span class="b ${i.priority}">${i.priority}</span>
       ${i.dispatched?' 🚁 dispatched':' logged'}
       <div class="m">${i.node_name} · severity ${i.severity} · audio ${i.audio_score}<br>
         ${new Date(i.ts*1000).toLocaleTimeString()} · ${i.mission_id||'no mission'}</div>
     </div>`).join('');
  }
 }catch(e){}
 setTimeout(pollInc, 900);
}
(async()=>{ try{ const ns=await (await fetch('/nodes')).json();
  ns.forEach(n=>L.circleMarker([n.lat,n.lon],{radius:6,color:'#5ea9ff',fillOpacity:.7})
    .bindTooltip('node '+n.node_id+' '+n.name).addTo(map)); }catch(e){} })();
fetch('/detector').then(r=>r.json()).then(d=>{
  const yam=d.backend==='yamnet';
  document.getElementById('detbadge').innerHTML =
    (yam?'✅ ':'⚙️ ')+'Detector: <span style="color:'+(yam?'#34d399':'#f5b14c')+'">'+d.name+'</span>';
}).catch(()=>{});
pollFleet(); pollDrone(); pollInc();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return brutalist_html(
        DASHBOARD_HTML.replace("%TEST_LAT%", str(CONFIG.test_lat))
        .replace("%TEST_LON%", str(CONFIG.test_lon))
    )
