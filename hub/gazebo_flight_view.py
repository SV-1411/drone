"""Dedicated geographic viewer for the real Gazebo / ArduPilot F450 runtime.

This intentionally replaces only ``/drone-flight``.  It does not share the
hardware-breakdown page or accept the hub's browser-simulation fallback state.
"""
from __future__ import annotations

import os

from fastapi.responses import HTMLResponse


STUDIO_CONTROL_URL = os.environ.get(
    "GAZEBO_CONTROL_URL",
    "https://8000-01m08b33gb41qz7hynmx9c8x8t.cloudspaces.litng.ai",
).rstrip("/")


def attach(app):
    # Older presentation viewers registered this same route. Remove their
    # routes explicitly so the Gazebo-only view is unambiguous.
    for route in list(app.router.routes):
        if getattr(route, "path", None) == "/drone-flight":
            app.router.routes.remove(route)

    @app.get("/drone-flight", response_class=HTMLResponse)
    def gazebo_flight_page():
        return HTML.replace("__GAZEBO_CONTROL_URL__", STUDIO_CONTROL_URL)


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanniKawachh | Gazebo F450 Flight Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
 integrity="sha256-p4NxAoJBhIINfQxkM6uQ3nZ6D/9cU9e6o5h1K0P7v+I=" crossorigin="">
<style>
:root{--bg:#061018;--panel:#08141df0;--line:#284854;--txt:#edf8fa;--muted:#8da8b2;--green:#35e2b3;--amber:#ffbc5b;--red:#ff6f7d;--cyan:#56dfff}*{box-sizing:border-box}html,body,#map{width:100%;height:100%;margin:0;background:var(--bg);font:13px Inter,Segoe UI,Arial,sans-serif;color:var(--txt)}.panel{position:fixed;z-index:1000;right:16px;top:16px;width:min(390px,calc(100vw - 32px));padding:14px;background:var(--panel);border:1px solid var(--line);border-radius:13px;box-shadow:0 14px 36px #0008;backdrop-filter:blur(9px)}.brand{font-size:19px;font-weight:900}.sub{color:var(--muted);font-size:11px;line-height:1.45;margin:4px 0 12px}.state{display:flex;align-items:center;gap:8px;margin:8px 0 12px;font-weight:800}.dot{width:9px;height:9px;border-radius:50%;background:#687982}.dot.live{background:var(--green);box-shadow:0 0 12px #35e2b3}.dot.warn{background:var(--amber)}.grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}.metric{background:#0b2029;border-radius:8px;padding:9px}.metric span{display:block;font-size:9px;letter-spacing:.1em;color:var(--muted)}.metric b{display:block;margin-top:3px;font-size:16px;font-variant-numeric:tabular-nums}.section{margin-top:11px;padding-top:10px;border-top:1px solid #1b3540}.row{display:flex;justify-content:space-between;margin:6px 0;gap:10px}.row span{color:var(--muted)}.row b{text-align:right}.controls{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:12px}.btn{border:1px solid var(--line);border-radius:8px;padding:9px;background:#102633;color:#fff;font-weight:800;cursor:pointer}.btn.primary{background:#0c2f25;border-color:#2a785f}.btn.warn{background:#2a1f14;border-color:#76552c}.btn:hover{filter:brightness(1.12)}#notice{margin:10px 0 0;color:var(--muted);font-size:10px;line-height:1.4}.drone-pin{font-size:31px;line-height:31px;color:#f7fbfc;text-shadow:0 2px 5px #000;transform-origin:50% 50%}.leaflet-control-attribution{background:#07131bcc!important;color:#b3cbd2!important}.leaflet-control-attribution a{color:#7edff6!important}@media(max-width:700px){.panel{left:10px;right:10px;top:10px;width:auto}}
</style>
</head>
<body>
<div id="map"></div>
<aside class="panel">
 <div class="brand">Gazebo F450 Flight</div>
 <div class="sub">Live map interface for the real ArduPilot SITL + Gazebo Harmonic aircraft. Browser-simulation telemetry is intentionally rejected.</div>
 <div class="state"><i id="dot" class="dot warn"></i><span id="state">Waiting for Gazebo telemetry</span></div>
 <div class="grid"><div class="metric"><span>FLIGHT MODE</span><b id="mode">—</b></div><div class="metric"><span>ALTITUDE AGL</span><b id="alt">—</b></div><div class="metric"><span>GROUND SPEED</span><b id="speed">—</b></div><div class="metric"><span>MOTORS</span><b id="motors">—</b></div></div>
 <div class="section"><div class="row"><span>Source</span><b id="source">Awaiting bridge</b></div><div class="row"><span>Mission</span><b id="mission">—</b></div><div class="row"><span>Route samples</span><b id="samples">0</b></div><div class="row"><span>Payload</span><b id="payload">Secured</b></div></div>
 <div class="controls"><button class="btn primary" id="start">Start Gazebo runtime</button><button class="btn" id="follow">Follow: on</button><button class="btn" id="fit">Fit mission</button><button class="btn warn" id="stop">Stop runtime</button></div>
 <p id="notice">Open this route to see the independent physics flight interface. Start initializes the remote Studio runtime.</p>
</aside>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
(()=>{const CONTROL='__GAZEBO_CONTROL_URL__', $=id=>document.getElementById(id), map=L.map('map',{zoomControl:false}).setView([21.1458,79.0882],13);L.control.zoom({position:'bottomleft'}).addTo(map);L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles © Esri'}).addTo(map);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,opacity:.18,attribution:'© OpenStreetMap'}).addTo(map);const icon=L.divIcon({className:'',html:'<div class="drone-pin">▲</div>',iconSize:[32,32],iconAnchor:[16,16]}),drone=L.marker([21.1458,79.0882],{icon,opacity:0,keyboard:false}).addTo(map),trail=L.polyline([],{color:'#56dfff',weight:4,opacity:.9}).addTo(map);let home,target,follow=true,latest,lastPoint,framed=false;const number=n=>typeof n==='number'&&Number.isFinite(n),fmt=(n,u)=>number(n)?n.toFixed(1)+u:'—';function mark(kind,point){if(!Array.isArray(point)||point.length!==2)return;const color=kind==='home'?'#35e2b3':'#ffbc5b',label=kind==='home'?'Launch / RTL home':'Distress target',m=L.circleMarker(point,{radius:7,color,weight:2,fillColor:color,fillOpacity:.8}).bindTooltip(label);if(kind==='home'){if(home)map.removeLayer(home);home=m.addTo(map)}else{if(target)map.removeLayer(target);target=m.addTo(map)}}function status(text,live){$('state').textContent=text;$('dot').className='dot '+(live?'live':'warn')}function apply(payload){if(!payload||payload.source!=='ARDUPILOT_SITL_GAZEBO'||!payload.connected||!payload.state){status('Waiting for real Gazebo telemetry',false);$('source').textContent=payload&&payload.source||'Unavailable';return}const d=payload.state;if(!number(d.lat)||!number(d.lon)){status('Bridge connected; waiting for GPS',false);return}latest=d;const point=[d.lat,d.lon],moved=!lastPoint||Math.abs(point[0]-lastPoint[0])>1e-7||Math.abs(point[1]-lastPoint[1])>1e-7;if(moved){trail.addLatLng(point);lastPoint=point}drone.setLatLng(point).setOpacity(1);const heading=number(d.heading_deg)?d.heading_deg:0,el=drone.getElement();if(el){const p=el.querySelector('.drone-pin');if(p)p.style.transform='rotate('+heading+'deg)'}mark('home',d.home);mark('target',d.target);if(!framed&&(home||target)){fit();framed=true}if(follow)map.panTo(point,{animate:true,duration:.45});$('mode').textContent=d.flight_mode||d.state||'—';$('alt').textContent=fmt(d.altitude_m,' m');$('speed').textContent=fmt(d.ground_speed_ms,' m/s');$('motors').textContent=d.motors_active?'Active':'Idle';$('source').textContent=payload.source;$('mission').textContent=d.mission_id||'—';$('samples').textContent=trail.getLatLngs().length;$('payload').textContent=d.kit_dropped?'Delivered':'Secured';$('notice').textContent='Live bridge update · '+new Date().toLocaleTimeString();status((d.armed?'Armed':'Disarmed')+' · '+(d.flight_mode||d.state||'Ready'),true)}function fit(){const items=[drone,home,target].filter(Boolean);if(items.length)map.fitBounds(L.featureGroup(items).getBounds(),{padding:[60,60],maxZoom:16})}async function poll(){try{apply(await (await fetch('/sitl-status',{cache:'no-store'})).json())}catch(e){status('Hub telemetry temporarily unavailable',false)}setTimeout(poll,1200)}async function control(path,method='GET'){try{const r=await fetch(CONTROL+path,{method,mode:'cors'});if(!r.ok)throw Error('HTTP '+r.status);$('notice').textContent='Studio: '+await r.text()}catch(e){$('notice').textContent='Studio control unavailable; wake the Lightning Studio then retry.'}}$('start').onclick=()=>control('/start');$('stop').onclick=()=>control('/stop','POST');$('fit').onclick=fit;$('follow').onclick=()=>{follow=!follow;$('follow').textContent='Follow: '+(follow?'on':'off')};poll()})()
</script>
</body>
</html>'''
