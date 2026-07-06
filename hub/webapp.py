"""Hub web app — clip receiver + police dashboard.

Endpoints:
    POST/PUT /clip/{node_id}/{counter}   node uploads its 4 s WAV evidence clip
    GET      /incidents                  JSON alert log (for the dashboard)
    GET      /nodes                      registered sensing nodes
    GET      /                           live police map (Leaflet) + audible alarm

The map polls /incidents once a second; a newly *dispatched* incident pans the
map, drops a red marker and sounds the alarm. Map tiles come from OSM, so the
police station needs internet for the basemap only — alerts themselves arrive
over LoRa. (Offline tile cache = future work.)
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from .config import CONFIG

log = logging.getLogger("hub.web")

app = FastAPI(title="VanniKawachh hub")


@app.post("/clip/{node_id}/{counter}")
@app.put("/clip/{node_id}/{counter}")
async def upload_clip(node_id: int, counter: int, request: Request):
    os.makedirs(CONFIG.clips_dir, exist_ok=True)
    body = await request.body()
    path = os.path.join(CONFIG.clips_dir, f"{node_id}_{counter}.wav")
    with open(path, "wb") as f:
        f.write(body)
    log.info("clip stored: %s (%d bytes)", path, len(body))
    return {"ok": True, "bytes": len(body)}


@app.get("/incidents")
def incidents():
    pipe = getattr(app.state, "pipeline", None)
    if pipe is None:
        return []
    return [
        {
            "ts": i.ts, "node_id": i.alert.node_id, "node_name": i.node_name,
            "lat": i.lat, "lon": i.lon, "event": i.alert.event_name,
            "audio_score": i.audio_score, "severity": i.severity,
            "priority": i.priority, "dispatched": i.dispatched,
            "mission_id": i.mission_id,
        }
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


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>VanniKawachh — Police Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  body{margin:0;font-family:Segoe UI,sans-serif;display:flex;height:100vh}
  #map{flex:1}
  #panel{width:360px;overflow-y:auto;background:#101319;color:#eceff3;padding:14px}
  h1{font-size:16px;margin:0 0 4px} .sub{color:#848e9c;font-size:12px;margin-bottom:12px}
  .inc{border:1px solid #39414e;border-radius:8px;padding:10px;margin-bottom:8px}
  .inc.dispatched{border-color:#ff6b6b;background:#2a1416}
  .inc b{font-size:14px} .inc .meta{color:#848e9c;font-size:12px;margin-top:4px}
  .badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600}
  .high{background:#ff6b6b;color:#fff} .normal{background:#f5b14c;color:#222}
</style></head><body>
<div id="panel">
  <h1>VanniKawachh — Live Alerts</h1>
  <div class="sub">Acoustic distress network · hub dashboard</div>
  <div id="list">No incidents yet.</div>
</div>
<div id="map"></div>
<script>
const map = L.map('map').setView([28.6139, 77.2090], 14);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            {attribution:'&copy; OpenStreetMap'}).addTo(map);
let seen = 0, nodeLayer = null;
function beep(){
  const ctx = new (window.AudioContext||window.webkitAudioContext)();
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.connect(g); g.connect(ctx.destination);
  o.frequency.value = 880; g.gain.value = 0.3;
  o.start(); setTimeout(()=>{o.frequency.value=660}, 200);
  setTimeout(()=>{o.stop(); ctx.close()}, 900);
}
async function loadNodes(){
  const r = await fetch('/nodes'); const ns = await r.json();
  ns.forEach(n => L.circleMarker([n.lat, n.lon],
      {radius:6, color:'#5ea9ff', fillOpacity:0.7})
    .bindTooltip(`node ${n.node_id} — ${n.name}`).addTo(map));
  if (ns.length) map.setView([ns[0].lat, ns[0].lon], 15);
}
async function poll(){
  try{
    const r = await fetch('/incidents'); const inc = await r.json();
    if (inc.length !== seen){
      const fresh = inc.slice(seen); seen = inc.length;
      fresh.forEach(i => {
        if (i.dispatched){
          L.marker([i.lat, i.lon]).addTo(map)
           .bindPopup(`<b>${i.event}</b> @ ${i.node_name}<br>severity ${i.severity}<br>mission ${i.mission_id||'-'}`)
           .openPopup();
          map.setView([i.lat, i.lon], 16);
          beep();
        }
      });
      const list = document.getElementById('list');
      list.innerHTML = inc.slice().reverse().map(i => `
        <div class="inc ${i.dispatched?'dispatched':''}">
          <b>${i.event}</b> <span class="badge ${i.priority}">${i.priority}</span>
          ${i.dispatched ? ' 🚁 drone dispatched' : ' logged'}
          <div class="meta">node ${i.node_id} (${i.node_name}) ·
            severity ${i.severity} · audio ${i.audio_score}<br>
            ${new Date(i.ts*1000).toLocaleTimeString()} ·
            ${i.mission_id ? 'mission '+i.mission_id : 'no mission'}</div>
        </div>`).join('');
    }
  }catch(e){ /* hub restarting — keep polling */ }
  setTimeout(poll, 1000);
}
loadNodes(); poll();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML
