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
from .sim_drone import PhoneDrone, SimDrone, SimDispatcher

log = logging.getLogger("hub.web")

app = FastAPI(title="VanniKawachh hub")

# Two ways to visualise the response:
#  sim_drone   auto-animated drone (single-phone test, no second device)
#  phone_drone a second phone reporting its real GPS as it moves (multi-phone)
sim_drone = SimDrone()
sim_dispatcher = SimDispatcher(sim_drone)
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

    Runs the trained model for its opinion, but also keeps a loudness gate so a
    genuine shout still triggers even if the (bootstrap-trained) model misses
    it. Returns (triggered, label, confidence, event_code)."""
    rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
    loud = min(1.0, rms / 0.06)
    model = _stage1()
    if model is not None:
        try:
            cls, conf = model.infer(audio)
            if cls != 0 and conf >= 0.60:
                return True, CLASSES[cls], conf, EVENT_CODE.get(cls, 1)
        except Exception as exc:
            log.warning("stage-1 infer failed: %s", exc)
    if loud >= 0.55:
        return True, "loud-distress", loud, 1
    return False, "background", loud, 0


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

    triggered, label, conf, event = stage1_phone(audio)
    if not triggered:
        return {"ok": True, "distress": False, "stage1": label,
                "confidence": round(conf, 2)}

    pipeline = getattr(app.state, "pipeline", None)
    if pipeline is None:
        return {"ok": False, "error": "hub pipeline not attached"}
    inc = pipeline.process_clip(lat, lon, path, conf, event, pir=bool(pir),
                                light=25, node_name="phone-node",
                                dispatcher=sim_dispatcher)
    if inc.dispatched:
        # also hand the incident to a drone phone, if one is connected
        phone_drone.assign(lat, lon, inc.mission_id, "phone-node")
    log.info("PHONE alert %s conf=%.2f -> severity %.2f dispatched=%s",
             label, conf, inc.severity, inc.dispatched)
    return {"ok": True, "distress": True, "stage1": label,
            "confidence": round(conf, 2), "audio_score": round(inc.audio_score, 2),
            "severity": round(inc.severity, 2), "dispatched": inc.dispatched,
            "mission_id": inc.mission_id, "lat": lat, "lon": lon}


@app.get("/drone_state")
def drone_state():
    # prefer a live drone phone; fall back to the auto sim drone
    return phone_drone.snapshot() if phone_drone.fresh() else sim_drone.snapshot()


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
         "audio_score": i.audio_score, "severity": i.severity,
         "priority": i.priority, "dispatched": i.dispatched,
         "mission_id": i.mission_id}
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
 :root{--bg:#0b1220;--card:#111a2e;--line:#233150;--txt:#eaf0fb;--mut:#8ea0bf;
       --red:#ef4444;--grn:#22c55e;--blu:#3b82f6}
 *{box-sizing:border-box}
 body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;
      background:linear-gradient(180deg,#0b1220,#0d1627);color:var(--txt);
      padding:0 16px 30px;-webkit-tap-highlight-color:transparent}
 header{display:flex;align-items:center;gap:11px;padding:18px 2px 6px}
 .logo{width:38px;height:38px;border-radius:11px;display:flex;align-items:center;justify-content:center;
       background:linear-gradient(135deg,#6d5efc,#22c1c3)}
 .brand{font-weight:700;font-size:18px} .badge{margin-left:auto;font-size:11px;font-weight:600;
       color:#34d399;background:#0f2a1c;border:1px solid #1c6b3f;padding:4px 10px;border-radius:20px}
 .tag{color:var(--mut);font-size:13px;margin:2px 2px 14px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;
       margin:12px 0;box-shadow:0 8px 26px rgba(0,0,0,.28)}
 .lbl{font-size:11px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.7px;margin-bottom:9px}
 .row{display:flex;gap:8px}
 input{flex:1;padding:13px;border-radius:11px;border:1px solid var(--line);background:#0a1120;color:var(--txt);font-size:15px}
 .btn{border:0;border-radius:13px;padding:15px;font-size:15px;font-weight:600;color:#fff;width:100%}
 .btn.sm{width:auto;white-space:nowrap;padding:13px 16px}
 .ghost{background:#152238;border:1px solid var(--line);color:var(--txt)}
 .loc{margin-top:11px;font-size:13px;line-height:1.4} .loc b{color:#7cc4ff}
 .shout{background:linear-gradient(180deg,#f2564f,#d33a38);height:120px;font-size:21px;margin-top:6px;
        box-shadow:0 10px 26px rgba(239,68,68,.34)}
 .mic{background:var(--blu)} .mic.on{background:var(--grn)}
 .meter{height:6px;background:#0a1120;border-radius:4px;overflow:hidden;margin-top:11px}
 .meter>div{height:100%;width:0;background:var(--grn);transition:width .1s}
 .v{font-size:16px;font-weight:700} .ok{color:var(--grn)} .no{color:var(--red)}
 .mut{color:var(--mut);font-size:12px;font-weight:400}
</style></head><body>
<header>
 <div class="logo"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#fff"
   stroke-width="2.2" stroke-linecap="round"><path d="M4 12h0M8 8v8M12 4v16M16 8v8M20 12h0"/></svg></div>
 <div class="brand">VanniKawachh</div>
 <div class="badge">&#9679; NODE ONLINE</div>
</header>
<div class="tag">Acoustic distress sensing node</div>

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
<button class="btn mic" id="mic">&#127908; Start live microphone
 <div class="mut" style="color:#d5e6ff;margin-top:3px">real audio &middot; needs https</div></button>
<div class="meter"><div id="meter"></div></div>

<div class="card">
 <div class="lbl">Status</div>
 <div class="v" id="res">Ready. Set a location, then trigger distress.</div>
 <div class="mut" id="res2"></div>
</div>

<script>
let lat = %TEST_LAT%, lon = %TEST_LON%, micOn = false, ctx, proc, buf = [], sr = 16000;
const $ = id => document.getElementById(id);
function coords(){ lat = parseFloat($('lat').value)||lat; lon = parseFloat($('lon').value)||lon; }
function setLoc(text){ $('lat').value = lat; $('lon').value = lon;
  $('loc').innerHTML = text + '<br><span class="mut">' + lat.toFixed(5) + ', ' + lon.toFixed(5) + '</span>'; }
setLoc('Default test area'); coords(); $('lat').value = lat; $('lon').value = lon;
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
  const rate=16000, n=rate*2, a=new Float32Array(n);
  for(let i=0;i<n;i++){ const t=i/rate;
    const f=900+500*Math.sin(2*Math.PI*2.6*t);
    let s=0.5*Math.sin(2*Math.PI*f*t)+0.25*Math.sin(4*Math.PI*f*t);
    if(t>0.6&&t<1.5) s*=2.0; a[i]=Math.max(-1,Math.min(1, s+0.03*(Math.random()*2-1))); }
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
function show(j){
  const res=document.getElementById('res'), res2=document.getElementById('res2');
  if(!j.ok){ res.innerHTML='<span class=no>error</span>'; res2.textContent=j.error||''; return; }
  if(!j.distress){ res.innerHTML='no distress ('+j.stage1+')'; res2.textContent='confidence '+j.confidence; return; }
  res.innerHTML = j.dispatched ? '<span class=ok>DISTRESS - drone dispatched</span>'
                               : '<span class=no>distress, not dispatched</span>';
  res2.textContent = `stage1 ${j.stage1} ${j.confidence} | audio ${j.audio_score} | severity ${j.severity} | ${j.mission_id||''}`;
}
document.getElementById('shout').onclick = () => { send(synthScream()); };

document.getElementById('mic').onclick = async () => {
  if(micOn){ micOn=false; document.getElementById('mic').classList.remove('on');
    document.getElementById('mic').innerHTML='&#127908; Start live microphone'; if(ctx) ctx.close(); return; }
  try{
    const st = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1}});
    ctx = new AudioContext(); sr = ctx.sampleRate;
    const src = ctx.createMediaStreamSource(st);
    proc = ctx.createScriptProcessor(4096,1,1);
    proc.onaudioprocess = e => {
      const d = e.inputBuffer.getChannelData(0);
      let peak=0; for(let i=0;i<d.length;i++){ buf.push(d[i]); peak=Math.max(peak,Math.abs(d[i])); }
      document.getElementById('meter').style.width=Math.min(100,peak*140)+'%';
      if(buf.length >= sr*2){
        const win=buf.slice(0,sr*2); buf=[];
        const ratio=sr/16000, len=Math.floor(win.length/ratio), out=new Float32Array(len);
        for(let i=0;i<len;i++) out[i]=win[Math.floor(i*ratio)];
        send(out);
      }
    };
    src.connect(proc); proc.connect(ctx.destination);
    micOn=true; document.getElementById('mic').classList.add('on');
    document.getElementById('mic').innerHTML='Listening... (tap to stop)';
  }catch(err){ alert('Mic needs HTTPS. Use SIMULATE DISTRESS on http, or run the hub with a cert.'); }
};
</script></body></html>"""


@app.get("/node", response_class=HTMLResponse)
def node_page():
    return (NODE_HTML.replace("%TEST_LAT%", str(CONFIG.test_lat))
                     .replace("%TEST_LON%", str(CONFIG.test_lon)))


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
    return DRONE_HTML


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
 #panel{width:360px;overflow-y:auto;background:#0b1220;color:#eaf0fb;padding:16px}
 #map{flex:1}
 .hd{display:flex;align-items:center;gap:10px;margin-bottom:4px}
 .logo{width:34px;height:34px;border-radius:10px;display:flex;align-items:center;justify-content:center;
       background:linear-gradient(135deg,#6d5efc,#22c1c3)}
 .brand{font-weight:700;font-size:17px} .sub{color:#8ea0bf;font-size:12px;margin:0 0 12px 44px}
 #chip{display:inline-block;padding:5px 12px;border-radius:20px;font-size:12px;font-weight:600;
       background:#111a2e;border:1px solid #233150;margin-bottom:12px}
 .inc{border:1px solid #233150;border-radius:12px;padding:11px;margin-bottom:8px;background:#111a2e}
 .inc.d{border-color:#ef4444;background:#221018}
 .inc .m{color:#8ea0bf;font-size:11px;margin-top:4px;line-height:1.4}
 .b{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700}
 .high{background:#ef4444;color:#fff} .normal{background:#f5b14c;color:#1a1206}
 .drone{font-size:24px;filter:drop-shadow(0 2px 4px rgba(0,0,0,.4))}
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
  <div id="list">No incidents yet. Open <b>/node</b> on a phone and trigger a distress signal.</div>
 </div>
 <div id="map"></div>
</div>
<script>
const map = L.map('map').setView([%TEST_LAT%, %TEST_LON%], 15);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap'}).addTo(map);
let seen=0, curMid=null, droneM=null, homeM=null, targetM=null, pathL=null, kitM=null;
function beep(){ try{ const c=new (window.AudioContext||window.webkitAudioContext)();
  const o=c.createOscillator(), g=c.createGain(); o.connect(g); g.connect(c.destination);
  o.frequency.value=880; g.gain.value=.3; o.start();
  setTimeout(()=>o.frequency.value=660,200); setTimeout(()=>{o.stop();c.close()},800);}catch(e){} }
const droneIcon = L.divIcon({html:'<div class=drone>🚁</div>',className:'',iconSize:[26,26],iconAnchor:[13,13]});

async function pollDrone(){
 try{
  const d = await (await fetch('/drone_state')).json();
  document.getElementById('chip').textContent = 'drone: ' + (d.state||'idle').toLowerCase()
     + (d.mission_id? ' ('+d.mission_id+')':'');
  // A new mission: recenter the map on it and clear the previous kit marker.
  if(d.mission_id && d.mission_id !== curMid){
    curMid = d.mission_id;
    if(kitM){ map.removeLayer(kitM); kitM=null; }
    if(d.target) map.setView(d.target, 16);
  }
  if(d.target){
    if(!targetM){ targetM=L.marker(d.target).addTo(map).bindPopup('incident'); }
    else targetM.setLatLng(d.target);
    if(d.home){ if(!homeM){ homeM=L.circleMarker(d.home,{radius:5,color:'#5ea9ff'}).addTo(map).bindPopup('drone base'); } else homeM.setLatLng(d.home); }
  }
  if(d.lat && d.state!=='IDLE'){
    if(!droneM) droneM=L.marker([d.lat,d.lon],{icon:droneIcon}).addTo(map);
    else droneM.setLatLng([d.lat,d.lon]);
    droneM.bindTooltip(d.state);
    if(d.home){ const pts=[d.home,[d.lat,d.lon]];
      if(!pathL) pathL=L.polyline(pts,{color:'#e5484d',dashArray:'5,6'}).addTo(map); else pathL.setLatLngs(pts); }
  }
  if(d.kit_dropped && d.target && !kitM){
    kitM=L.marker(d.target).addTo(map).bindPopup('📦 first-aid kit dropped').openPopup();
  }
 }catch(e){}
 setTimeout(pollDrone, 400);
}
async function pollInc(){
 try{
  const inc = await (await fetch('/incidents')).json();
  if(inc.length!==seen){ const fresh=inc.slice(seen); seen=inc.length;
    fresh.forEach(i=>{ if(i.dispatched){ beep(); } });
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
pollDrone(); pollInc();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return (DASHBOARD_HTML.replace("%TEST_LAT%", str(CONFIG.test_lat))
                          .replace("%TEST_LON%", str(CONFIG.test_lon)))
