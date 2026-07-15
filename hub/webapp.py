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
 body{margin:0;font-family:Segoe UI,system-ui,sans-serif;background:#0e1117;color:#eceff3;
      text-align:center;padding:18px;-webkit-tap-highlight-color:transparent}
 h1{font-size:19px;margin:6px 0} .sub{color:#8b95a2;font-size:13px;margin-bottom:18px}
 button{font-size:18px;font-weight:600;border:0;border-radius:14px;padding:18px;width:100%;
        margin:8px 0;color:#fff}
 #shout{background:#e5484d;height:120px;font-size:22px}
 #mic{background:#2a6ef0} #mic.on{background:#3a9d6b}
 .card{background:#161b22;border:1px solid #2a2f38;border-radius:12px;padding:14px;margin:12px 0;
       text-align:left}
 .k{color:#8b95a2;font-size:12px} .v{font-size:16px;font-weight:600}
 .ok{color:#3a9d6b} .no{color:#e5484d} input{width:46%;padding:8px;border-radius:8px;border:1px solid #2a2f38;
       background:#0e1117;color:#eceff3}
 .lvl{height:8px;background:#2a2f38;border-radius:4px;overflow:hidden;margin-top:8px}
 .lvl>div{height:100%;width:0;background:#3a9d6b}
</style></head><body>
<h1>VanniKawachh - Sensing Node</h1>
<div class="sub">This phone acts as a pole microphone. Trigger a distress event and
watch the dashboard respond.</div>

<button id="shout">SIMULATE DISTRESS<br><span style="font-size:13px;font-weight:400">
(sends a scream clip - works anywhere)</span></button>
<button id="mic">Start live mic<br><span style="font-size:12px;font-weight:400">
(real audio - needs https)</span></button>
<div class="lvl"><div id="meter"></div></div>

<div class="card">
  <div class="k">Incident location (lat, lon)</div>
  <div><input id="lat" value=""> <input id="lon" value=""></div>
  <div class="k" style="margin-top:6px" id="gps">using default test location</div>
</div>

<div class="card">
  <div class="k">Last result</div>
  <div class="v" id="res">idle - tap SIMULATE DISTRESS</div>
  <div class="k" id="res2"></div>
</div>

<script>
let lat = %TEST_LAT%, lon = %TEST_LON%, micOn = false, ctx, proc, buf = [], sr = 16000;
document.getElementById('lat').value = lat.toFixed(5);
document.getElementById('lon').value = lon.toFixed(5);
function coords(){ lat = parseFloat(document.getElementById('lat').value)||lat;
  lon = parseFloat(document.getElementById('lon').value)||lon; }
if (navigator.geolocation) navigator.geolocation.getCurrentPosition(p => {
  lat = p.coords.latitude; lon = p.coords.longitude;
  document.getElementById('lat').value = lat.toFixed(5);
  document.getElementById('lon').value = lon.toFixed(5);
  document.getElementById('gps').textContent = 'using this phone GPS';
}, () => {});

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
  const r = await fetch(`/phone-alert?lat=${lat}&lon=${lon}&pir=1`,
    {method:'POST', headers:{'Content-Type':'audio/wav'}, body: wavBlob(samples,16000)});
  const j = await r.json(); show(j);
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
    document.getElementById('mic').innerHTML='Start live mic'; if(ctx) ctx.close(); return; }
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
 body{margin:0;font-family:Segoe UI,system-ui,sans-serif;background:#0e1117;color:#eceff3;
      text-align:center;padding:18px}
 h1{font-size:19px;margin:6px 0} .sub{color:#8b95a2;font-size:13px;margin-bottom:14px}
 .card{background:#161b22;border:1px solid #2a2f38;border-radius:12px;padding:14px;margin:10px 0;text-align:left}
 .k{color:#8b95a2;font-size:12px} .v{font-size:16px;font-weight:600}
 button{font-size:16px;font-weight:600;border:0;border-radius:12px;padding:15px;width:100%;margin:6px 0;color:#fff}
 #gps{background:#2a6ef0} #gps.on{background:#3a9d6b} #step{background:#5a5f6a}
 #kit{background:#e5a23d;color:#222} #rtl{background:#7a4fd0} .big{font-size:30px;font-weight:700}
</style></head><body>
<h1>VanniKawachh - Drone Unit</h1>
<div class="sub">This phone is the drone. Walk toward the incident; the dashboard
tracks you. Or tap STEP to advance without moving.</div>

<div class="card">
  <div class="k">Assigned incident</div>
  <div class="v" id="tgt">waiting for an alert...</div>
  <div class="k" style="margin-top:6px">distance</div>
  <div class="big" id="dist">--</div>
  <div class="k">state</div><div class="v" id="st">IDLE</div>
</div>

<button id="gps">Follow my GPS<br><span style="font-size:12px;font-weight:400">(real movement - needs https)</span></button>
<button id="step">STEP toward incident (20%)</button>
<button id="kit">DROP FIRST-AID KIT</button>
<button id="rtl">RETURN TO BASE</button>

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
async function report(state){
 if(!me) return;
 let d = target? hav(me,target):null;
 let s = state || (d===null?'IDLE': d<20?'HOVERING':'ENROUTE');
 document.getElementById('st').textContent=s;
 document.getElementById('dist').textContent = d===null?'--':(d<1000?d.toFixed(0)+' m':(d/1000).toFixed(2)+' km');
 try{ await fetch(`/drone-report?lat=${me[0]}&lon=${me[1]}&state=${s}&kit=${kit?1:0}`,{method:'POST'}); }catch(e){}
}
document.getElementById('step').onclick=()=>{ if(!target) return;
  if(!me) me=[target[0]+0.005,target[1]];
  me=[me[0]+(target[0]-me[0])*0.2, me[1]+(target[1]-me[1])*0.2]; report(); };
document.getElementById('kit').onclick=()=>{ kit=true; report('DELIVERING'); };
document.getElementById('rtl').onclick=()=>{ report('RTL'); };
document.getElementById('gps').onclick=()=>{
  const b=document.getElementById('gps');
  if(watch){ navigator.geolocation.clearWatch(watch); watch=null; b.classList.remove('on'); b.innerHTML='Follow my GPS'; return; }
  if(!navigator.geolocation){ alert('No geolocation. Use STEP, or serve over https.'); return; }
  watch=navigator.geolocation.watchPosition(p=>{ me=[p.coords.latitude,p.coords.longitude]; report(); },
    e=>{ alert('GPS needs https on a phone. Use the STEP button on http.'); },
    {enableHighAccuracy:true, maximumAge:1000});
  b.classList.add('on'); b.innerHTML='Following GPS (tap to stop)';
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
 html,body{margin:0;height:100%;font-family:Segoe UI,system-ui,sans-serif}
 #app{display:flex;height:100vh}
 #panel{width:340px;overflow-y:auto;background:#101319;color:#eceff3;padding:14px;box-sizing:border-box}
 #map{flex:1}
 h1{font-size:16px;margin:0 0 2px} .sub{color:#848e9c;font-size:12px;margin-bottom:8px}
 #chip{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;
       background:#2a2f38;margin-bottom:10px}
 .inc{border:1px solid #39414e;border-radius:8px;padding:9px;margin-bottom:7px}
 .inc.d{border-color:#e5484d;background:#2a1416}
 .inc .m{color:#848e9c;font-size:11px;margin-top:3px}
 .b{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;font-weight:600}
 .high{background:#e5484d;color:#fff} .normal{background:#f5b14c;color:#222}
 .drone{font-size:22px}
 @media(max-width:720px){ #app{flex-direction:column} #panel{width:auto;height:44vh;order:2}
   #map{height:56vh;order:1} }
</style></head><body>
<div id="app">
 <div id="panel">
  <h1>VanniKawachh - Live Alerts</h1>
  <div class="sub">Acoustic distress network - hub dashboard</div>
  <div id="chip">drone: idle</div>
  <div id="list">No incidents yet. Open <b>/node</b> on a phone and tap SIMULATE DISTRESS.</div>
 </div>
 <div id="map"></div>
</div>
<script>
const map = L.map('map').setView([%TEST_LAT%, %TEST_LON%], 15);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap'}).addTo(map);
let seen=0, centered=false, droneM=null, homeM=null, targetM=null, pathL=null, kitM=null;
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
  if(d.target){
    if(!targetM){ targetM=L.marker(d.target).addTo(map).bindPopup('incident'); }
    else targetM.setLatLng(d.target);
    if(!homeM && d.home){ homeM=L.circleMarker(d.home,{radius:5,color:'#5ea9ff'}).addTo(map).bindPopup('drone base'); }
    if(!centered){ map.setView(d.target,16); centered=true; }
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
  if(d.state==='COMPLETED' || d.state==='IDLE'){ if(kitM){ setTimeout(()=>{ if(kitM){map.removeLayer(kitM); kitM=null;} },4000);} }
 }catch(e){}
 setTimeout(pollDrone, 400);
}
async function pollInc(){
 try{
  const inc = await (await fetch('/incidents')).json();
  if(inc.length!==seen){ const fresh=inc.slice(seen); seen=inc.length;
    fresh.forEach(i=>{ if(i.dispatched){ beep(); if(!centered){map.setView([i.lat,i.lon],16);centered=true;} } });
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
