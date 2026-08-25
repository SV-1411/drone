"""Browser 3D + map hardware simulation for VanniKawachh.

The page is a visualization layer on top of the deployed hub's /drone_state.
It is deliberately synchronized to the same SimDrone state used by the existing
Wokwi -> hub -> dispatch demo. ArduPilot SITL remains the flight-physics proof.
"""
from fastapi.responses import HTMLResponse


def attach(app):
    @app.get("/drone-sim", response_class=HTMLResponse)
    def drone_sim_page():
        return DRONE_SIM_HTML


DRONE_SIM_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanniKawachh | Drone Hardware Simulation</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{--bg:#050b11;--panel:#08151f;--line:#203747;--text:#eaf3f8;--muted:#8da4b4;--cyan:#32e0b0;--amber:#ffb24a;--red:#ff5f6d;--blue:#69adff}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 390px;width:100vw;height:100vh}
#left{display:grid;grid-template-rows:58% 42%;min-width:0;min-height:0;background:#061018}
#threeWrap,#mapWrap{position:relative;min-height:0;overflow:hidden;border-bottom:1px solid #17303f}
#stage,#map{width:100%;height:100%}.hud{position:absolute;z-index:20;left:14px;right:14px;top:12px;display:flex;justify-content:space-between;pointer-events:none}.pill{background:#07131ee8;border:1px solid var(--line);border-radius:999px;padding:8px 12px;font-size:11px;color:var(--muted);backdrop-filter:blur(8px)}.pill b{color:var(--text)}
.mapBadge{position:absolute;z-index:500;left:12px;bottom:12px;background:#07131ee8;border:1px solid var(--line);padding:7px 10px;border-radius:9px;font-size:11px}.mapBadge b{color:var(--cyan)}
#side{background:#07121bf7;border-left:1px solid var(--line);padding:14px;overflow:auto}.title{font-size:19px;font-weight:850}.sub{font-size:11px;color:var(--muted);line-height:1.45;margin-top:3px}.card{background:linear-gradient(180deg,#0d1c27,#09151e);border:1px solid var(--line);border-radius:13px;padding:11px;margin:10px 0}.label{font-size:10px;color:var(--muted);letter-spacing:.1em}.state{font-size:24px;font-weight:900;margin-top:4px}.live{color:var(--cyan)}.warn{color:var(--amber)}.bad{color:var(--red)}.row{display:flex;justify-content:space-between;gap:10px;margin-top:7px;font-size:12px}.value{font-weight:750;text-align:right}.ok{color:var(--cyan)}
.sequence{font-size:11px;line-height:1.65}.sequence div{padding:3px 0;color:#617786}.sequence .done{color:var(--cyan)}.sequence .active{color:var(--amber);font-weight:800}.sequence .queued{color:#617786}.buttons{display:grid;grid-template-columns:1fr 1fr;gap:7px}.buttons button{border:1px solid var(--line);border-radius:9px;padding:11px 8px;background:#122432;color:var(--text);font-weight:800;cursor:pointer}.buttons button:hover{background:#19374b}.buttons .primary{border-color:#276b5b;background:#0f2b24}.buttons .warnBtn{border-color:#705327;background:#2a2113}
.flow{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:4px;align-items:center;text-align:center;font-size:8px}.node{padding:7px 3px;border:1px solid var(--line);border-radius:8px;background:#0c1a24;color:#a7bdca}.arrow{color:var(--cyan)}#log{height:105px;overflow:auto;background:#061019;border:1px solid #142734;border-radius:8px;padding:7px;font:10px/1.5 ui-monospace,Consolas,monospace;color:#8fb9cc}.foot{font-size:9px;color:#647b89;line-height:1.45;margin-top:8px}
@media(max-width:900px){#app{grid-template-columns:1fr}#side{position:absolute;right:0;top:0;bottom:0;width:min(390px,94vw);z-index:50;box-shadow:-15px 0 35px #000b}#left{grid-template-rows:60% 40%}}
</style>
</head>
<body>
<div id="app">
<section id="left">
 <div id="threeWrap"><div class="hud"><div class="pill"><b>VANNIKAWACHH</b> · 3D DRONE HARDWARE</div><div class="pill">SOURCE: <b id="source">LIVE HUB</b></div></div><canvas id="stage"></canvas></div>
 <div id="mapWrap"><div id="map"></div><div class="mapBadge">LIVE ROUTE · <b id="mapState">IDLE</b> · marker and route use the same /drone_state feed</div></div>
</section>
<aside id="side">
 <div><div class="title">Virtual Drone Unit</div><div class="sub">One synchronized mission drives the 3D aircraft, live map, rotor animation, navigation, payload action and checklist.</div></div>
 <div class="card"><div class="label">FLIGHT STATE</div><div id="state" class="state live">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="value">—</span></div><div class="row"><span>Altitude</span><span id="alt" class="value">0.0 m</span></div><div class="row"><span>Speed</span><span id="speed" class="value">0.0 m/s</span></div></div>
 <div class="card"><div class="label">NAVIGATION</div><div class="row"><span>Home</span><span id="home" class="value">—</span></div><div class="row"><span>Target</span><span id="target" class="value">—</span></div><div class="row"><span>Position</span><span id="pos" class="value">—</span></div><div class="row"><span>Distance</span><span id="dist" class="value">—</span></div></div>
 <div class="card"><div class="label">VIRTUAL HARDWARE</div><div class="row"><span>4 × BLDC / ESC</span><span id="rotors" class="value ok">OFF</span></div><div class="row"><span>Flight controller</span><span class="value ok">CONNECTED</span></div><div class="row"><span>GPS + compass</span><span class="value ok">LOCKED</span></div><div class="row"><span>Companion / link</span><span class="value ok">ONLINE</span></div><div class="row"><span>Payload servo</span><span id="servo" class="value">CLOSED</span></div><div class="row"><span>Health kit</span><span id="kit" class="value">SECURED</span></div></div>
 <div class="card"><div class="label">SIGNAL / HARDWARE CHAIN</div><div class="flow"><div class="node">ESP32<br>NODE</div><div class="arrow">→</div><div class="node">HUB<br>DISPATCH</div><div class="arrow">→</div><div class="node">FLIGHT<br>CONTROLLER</div><div class="arrow">→</div><div class="node">MOTORS<br>+ PAYLOAD</div></div></div>
 <div class="card"><div class="label">MISSION SEQUENCE · SYNCHRONIZED</div><div class="sequence"><div id="q1">○ Distress trigger</div><div id="q2">○ Arm / spin rotors</div><div id="q3">○ Takeoff</div><div id="q4">○ Fly to distress GPS</div><div id="q5">○ Hover at location</div><div id="q6">○ Open payload bay</div><div id="q7">○ Drop health kit</div><div id="q8">○ RTL / land</div></div></div>
 <div class="buttons"><button id="live" class="primary">LIVE HUB</button><button id="trigger">TEST HUB DISTRESS</button><button id="demo">RUN LOCAL DEMO</button><button id="reset" class="warnBtn">RESET VIEW</button></div>
 <div class="card"><div class="label">EVENT LOG</div><div id="log"></div></div>
 <div class="foot">LIVE HUB reads the deployed <b>/drone_state</b>. The 3D aircraft and map are synchronized to the same GPS/state samples. TEST HUB DISTRESS calls the deployed <b>/node-alert</b>. The visuals are a hardware/response simulation; ArduPilot SITL remains the flight-physics validation layer.</div>
</aside></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const $=id=>document.getElementById(id);
const log=m=>{const e=$('log');e.innerHTML+=`<div>${new Date().toLocaleTimeString()} · ${m}</div>`;e.scrollTop=e.scrollHeight};
const FALLBACK_HOME=[21.12330,79.04194], FALLBACK_TARGET=[21.12800,79.04700];
let live=true, demo=false, demoStart=0, last=null, lastMission=null, lastState='IDLE', pollTimer=null, missionView=false;
let worldMetersPerUnit=100, lastGPS=null, visualAltitude=0, targetAltitude=0, kitAnimating=false, kitDropStart=0;

/* ----------------------------- THREE -------------------------------- */
const scene=new THREE.Scene();scene.background=new THREE.Color(0x061018);scene.fog=new THREE.Fog(0x061018,45,120);
const camera=new THREE.PerspectiveCamera(42,1,.1,400);camera.position.set(12,9,15);
const renderer=new THREE.WebGLRenderer({canvas:$('stage'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.target.set(0,2,0);
scene.add(new THREE.HemisphereLight(0x9bcfff,0x15222b,2.2));const key=new THREE.DirectionalLight(0xffffff,3.0);key.position.set(8,15,8);key.castShadow=true;scene.add(key);
const grid=new THREE.GridHelper(120,60,0x1b3b4b,0x102936);scene.add(grid);
const pad=new THREE.Mesh(new THREE.CylinderGeometry(3.2,.2,.12,64),new THREE.MeshBasicMaterial({color:0x102a35}));pad.position.y=.05;scene.add(pad);
const ring=new THREE.Mesh(new THREE.TorusGeometry(3.2,.025,8,96),new THREE.MeshBasicMaterial({color:0x2ee0b0}));ring.rotation.x=Math.PI/2;ring.position.y=.13;scene.add(ring);
const targetBeacon=new THREE.Mesh(new THREE.CylinderGeometry(.12,.55,.35,32),new THREE.MeshBasicMaterial({color:0xff5f6d,transparent:true,opacity:.8}));targetBeacon.position.y=.12;scene.add(targetBeacon);targetBeacon.visible=false;
const routeMat=new THREE.LineBasicMaterial({color:0x69adff});let routeLine=null;
const drone=new THREE.Group();scene.add(drone);drone.position.set(0,.8,0);
const body=new THREE.Mesh(new THREE.BoxGeometry(1.7,.28,1.05),new THREE.MeshStandardMaterial({color:0x1d2d36,metalness:.65,roughness:.3}));body.castShadow=true;drone.add(body);
const top=new THREE.Mesh(new THREE.BoxGeometry(.9,.18,.65),new THREE.MeshStandardMaterial({color:0x32e0b0,metalness:.3,roughness:.35}));top.position.y=.22;drone.add(top);
const cam=new THREE.Mesh(new THREE.BoxGeometry(.28,.22,.28),new THREE.MeshStandardMaterial({color:0x101820,metalness:.5}));cam.position.set(0,-.05,.58);drone.add(cam);
const rotors=[],rotorCenters=[[-1.35,.12,-.78],[1.35,.12,-.78],[-1.35,.12,.78],[1.35,.12,.78]];
for(const [x,y,z] of rotorCenters){const arm=new THREE.Mesh(new THREE.BoxGeometry(1.9,.1,.12),new THREE.MeshStandardMaterial({color:0x607681,metalness:.6}));arm.position.set(x/2,.02,z/2);arm.rotation.y=Math.atan2(z,x);drone.add(arm);const g=new THREE.Group();g.position.set(x,y,z);const motor=new THREE.Mesh(new THREE.CylinderGeometry(.16,.16,.12,24),new THREE.MeshStandardMaterial({color:0x222b31,metalness:.8}));motor.rotation.x=Math.PI/2;g.add(motor);for(const a of [0,Math.PI/2]){const p=new THREE.Mesh(new THREE.BoxGeometry(.85,.035,.09),new THREE.MeshBasicMaterial({color:0x63a8ff,transparent:true,opacity:.62}));p.rotation.y=a;g.add(p)}drone.add(g);rotors.push(g)}
const bay=new THREE.Mesh(new THREE.BoxGeometry(.7,.18,.55),new THREE.MeshStandardMaterial({color:0x303b42,metalness:.4}));bay.position.y=-.25;drone.add(bay);
const kit=new THREE.Mesh(new THREE.BoxGeometry(.42,.3,.42),new THREE.MeshStandardMaterial({color:0xffb24a,metalness:.1}));kit.position.set(0,-.52,0);kit.visible=false;drone.add(kit);
const groundKit=new THREE.Mesh(new THREE.BoxGeometry(.42,.3,.42),new THREE.MeshStandardMaterial({color:0xffb24a}));groundKit.visible=false;scene.add(groundKit);
const shadow=new THREE.Mesh(new THREE.CircleGeometry(1.6,48),new THREE.MeshBasicMaterial({color:0x000000,transparent:true,opacity:.26}));shadow.rotation.x=-Math.PI/2;scene.add(shadow);
function resize(){const r=$('threeWrap').getBoundingClientRect();camera.aspect=r.width/r.height;camera.updateProjectionMatrix();renderer.setSize(r.width,r.height,false)}addEventListener('resize',resize);resize();

function hav(a,b){if(!a||!b)return 0;const R=6371000,rad=x=>x*Math.PI/180;const dLat=rad(b[0]-a[0]),dLon=rad(b[1]-a[1]);const x=Math.sin(dLat/2)**2+Math.cos(rad(a[0]))*Math.cos(rad(b[0]))*Math.sin(dLon/2)**2;return 2*R*Math.asin(Math.sqrt(x))}
function fmtCoord(v){return Array.isArray(v)?v.map(x=>Number(x).toFixed(5)).join(', '):'—'}
function fmtDist(m){return m<1000?Math.round(m)+' m':(m/1000).toFixed(2)+' km'}
function metersPerUnit(home,target){const d=Math.max(80,hav(home,target));return d/10}
function worldPoint(lat,lon,home){const latScale=111000,lonScale=111000*Math.cos(home[0]*Math.PI/180);return {x:(lon-home[1])*lonScale/worldMetersPerUnit,z:-(lat-home[0])*latScale/worldMetersPerUnit}}
function rebuildWorld(h,t){worldMetersPerUnit=metersPerUnit(h,t);const H=worldPoint(h[0],h[1],h),T=worldPoint(t[0],t[1],h);drone.position.set(H.x,.8,H.z);shadow.position.set(H.x,.12,H.z);targetBeacon.position.set(T.x,.12,T.z);targetBeacon.visible=true;grid.position.set((H.x+T.x)/2,0,(H.z+T.z)/2);pad.position.set(H.x,.05,H.z);ring.position.set(H.x,.13,H.z);if(routeLine)scene.remove(routeLine);routeLine=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(H.x,.18,H.z),new THREE.Vector3(T.x,.18,T.z)]),routeMat);scene.add(routeLine);camera.position.set(H.x+11,8,H.z+14);controls.target.set((H.x+T.x)/2,1,(H.z+T.z)/2);controls.update();}
function setText(id,v){$(id).textContent=v}
function setSequence(s,d){
 const order=['q1','q2','q3','q4','q5','q6','q7','q8'];
 const done=new Set();let active=null;
 if(d?.mission_id)done.add('q1');
 if(['ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s))done.add('q2');else if(s==='TAKEOFF')active='q2';
 if(['ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s))done.add('q3');else if(s==='TAKEOFF')active='q3';
 if(['HOVERING','DELIVERING','RTL','COMPLETED'].includes(s))done.add('q4');else if(s==='ENROUTE')active='q4';
 if(['DELIVERING','RTL','COMPLETED'].includes(s))done.add('q5');else if(s==='HOVERING')active='q5';
 if(d?.kit_dropped||['RTL','COMPLETED'].includes(s))done.add('q6');else if(s==='DELIVERING')active='q6';
 if(d?.kit_dropped)done.add('q7');else if(s==='DELIVERING')active='q7';
 if(s==='COMPLETED')done.add('q8');else if(s==='RTL')active='q8';
 order.forEach(id=>$(id).className=done.has(id)?'done':(id===active?'active':'queued'));
}
function applyState(d){if(!d)return;last=d;const s=d.state||'IDLE';
 setText('state',s);$('state').className='state '+(s==='FAILED'?'bad':(['TAKEOFF','ENROUTE','RTL'].includes(s)?'warn':'live'));
 setText('mapState',s);setText('mission',d.mission_id||'—');setText('home',fmtCoord(d.home));setText('target',fmtCoord(d.target));setText('pos',d.lat!=null?Number(d.lat).toFixed(5)+', '+Number(d.lon).toFixed(5):'—');setText('rotors',['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(s)?'SPINNING':'OFF');setText('servo',s==='DELIVERING'?'OPEN':'CLOSED');setText('kit',d.kit_dropped?'DROPPED':'SECURED');
 setText('alt',s==='TAKEOFF'?'5.0 m':(['ENROUTE','HOVERING','RTL'].includes(s)?'15.0 m':(s==='DELIVERING'?'3.0 m':'0.0 m')));setText('speed',['ENROUTE','RTL'].includes(s)?'8.0 m/s':(s==='TAKEOFF'?'3.0 m/s':'0.0 m/s'));setSequence(s,d);
 if(d.home&&d.target&&(d.mission_id!==lastMission||!missionView)){lastMission=d.mission_id;missionView=true;rebuildWorld(d.home,d.target);mapReset(d.home,d.target);log('Mission '+d.mission_id+' assigned · route built on map + 3D view')}
 const dist=d.lat!=null&&d.target?hav([d.lat,d.lon],d.target):null;setText('dist',dist==null?'—':fmtDist(dist));
 if(s!==lastState){log('State → '+s);lastState=s}
 updateMap(d);}

/* ------------------------------ LEAFLET ------------------------------ */
const map=L.map('map',{zoomControl:true,attributionControl:true}).setView(FALLBACK_HOME,13);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);
let homeM=null,targetM=null,droneM=null,routeM=null,trailM=null,trail=[];
const droneIcon=L.divIcon({html:'<div style="font-size:26px;filter:drop-shadow(0 2px 4px rgba(0,0,0,.55))">🚁</div>',className:'',iconSize:[30,30],iconAnchor:[15,15]});
const homeIcon=L.divIcon({html:'<div style="width:12px;height:12px;border-radius:50%;background:#69adff;border:2px solid #fff;box-shadow:0 0 10px #69adff"></div>',className:'',iconSize:[12,12],iconAnchor:[6,6]});
const targetIcon=L.divIcon({html:'<div style="width:14px;height:14px;border-radius:50%;background:#ff5f6d;border:2px solid #fff;box-shadow:0 0 14px #ff5f6d"></div>',className:'',iconSize:[14,14],iconAnchor:[7,7]});
function mapReset(h,t){if(homeM)map.removeLayer(homeM);if(targetM)map.removeLayer(targetM);if(droneM)map.removeLayer(droneM);if(routeM)map.removeLayer(routeM);if(trailM)map.removeLayer(trailM);trail=[];homeM=L.marker(h,{icon:homeIcon}).addTo(map).bindTooltip('DRONE BASE');targetM=L.marker(t,{icon:targetIcon}).addTo(map).bindTooltip('DISTRESS LOCATION');droneM=L.marker(h,{icon:droneIcon,zIndexOffset:1000}).addTo(map).bindTooltip('DRONE');routeM=L.polyline([h,t],{color:'#69adff',weight:3,dashArray:'7,7'}).addTo(map);trailM=L.polyline([],{color:'#32e0b0',weight:4,opacity:.9}).addTo(map);map.fitBounds([h,t],{padding:[25,25]})}
function updateMap(d){if(!d?.lat||!d?.lon)return;if(!droneM){const h=d.home||FALLBACK_HOME,t=d.target||d.home;mapReset(h,t)}droneM.setLatLng([d.lat,d.lon]);trail.push([d.lat,d.lon]);if(trail.length>160)trail.shift();if(trailM)trailM.setLatLngs(trail);if(d.state!=='IDLE'&&d.target&&['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(d.state)){map.panTo([d.lat,d.lon],{animate:true,duration:.25})}}

/* ------------------------------ DEMO --------------------------------- */
function makeDemoData(t){const H=FALLBACK_HOME,T=FALLBACK_TARGET;let d={mission_id:'LOCAL-DEMO',home:H,target:T,lat:H[0],lon:H[1],kit_dropped:false,state:'IDLE'};if(t>=1)d.state='TAKEOFF';if(t>=2.5){d.state='ENROUTE';const f=Math.min(1,(t-2.5)/5);d.lat=H[0]+(T[0]-H[0])*f;d.lon=H[1]+(T[1]-H[1])*f}if(t>=7.5){d.state='HOVERING';d.lat=T[0];d.lon=T[1]}if(t>=9.5){d.state='DELIVERING';d.lat=T[0];d.lon=T[1]}if(t>=11)d.kit_dropped=true;if(t>=12.5){d.state='RTL';const f=Math.min(1,(t-12.5)/5);d.lat=T[0]+(H[0]-T[0])*f;d.lon=T[1]+(H[1]-T[1])*f}if(t>=17.5){d.state='COMPLETED';d.lat=H[0];d.lon=H[1]}return d}
function startDemo(){live=false;demo=true;missionView=false;lastMission=null;lastState='IDLE';const start=performance.now();function tick(){const t=(performance.now()-start)/1000;const d=makeDemoData(t);if(!missionView){applyState(d)}else{applyState(d)}if(t<18.5)requestAnimationFrame(tick);else log('Local demo complete · switch to LIVE HUB for real Wokwi state')}requestAnimationFrame(tick);}

$('live').onclick=()=>{demo=false;live=true;missionView=false;lastMission=null;$('source').textContent='LIVE HUB';log('LIVE HUB connected');pollNow()};
$('demo').onclick=()=>{log('Starting synchronized local demo');startDemo()};
$('reset').onclick=()=>{demo=false;live=true;missionView=false;lastMission=null;lastState='IDLE';last=null;map.setView(FALLBACK_HOME,13);$('source').textContent='LIVE HUB';applyState({state:'IDLE',home:FALLBACK_HOME,target:null,lat:FALLBACK_HOME[0],lon:FALLBACK_HOME[1],kit_dropped:false});log('View reset');pollNow()};
$('trigger').onclick=async()=>{try{$('source').textContent='TRIGGERING…';const r=await fetch(`/node-alert?node=3D-SIM&lat=${FALLBACK_TARGET[0]}&lon=${FALLBACK_TARGET[1]}&event=1&conf=0.99&pir=1&light=30`,{method:'POST'});const j=await r.json();log(j.dispatched?'Hub dispatched '+j.mission_id:'Hub response: '+JSON.stringify(j));live=true;demo=false;missionView=false;lastMission=null;$('source').textContent='LIVE HUB';pollNow()}catch(e){log('Trigger failed: '+e.message)}};

async function pollNow(){if(!live)return;try{const r=await fetch('/drone_state?ts='+Date.now(),{cache:'no-store'});if(r.ok)applyState(await r.json());else $('source').textContent='HUB '+r.status}catch(e){$('source').textContent='HUB UNREACHABLE'}clearTimeout(pollTimer);pollTimer=setTimeout(pollNow,220)}
log('Ready · waiting for deployed /drone_state');pollNow();

/* 3D animation follows the same state/GPS as the map. No separate flight path. */
let clock=new THREE.Clock();function frame(){requestAnimationFrame(frame);const dt=Math.min(clock.getDelta(),.05);const d=last;let p=null;if(d?.lat!=null&&d?.home)p=worldPoint(d.lat,d.lon,d.home);const s=d?.state||'IDLE';
 if(p){let a=s==='DELIVERING'?3:(['ENROUTE','HOVERING','RTL'].includes(s)?15:(s==='TAKEOFF'?Math.min(15,5):0));const targetY=a;visualAltitude+=(targetY-visualAltitude)*Math.min(1,dt*7);drone.position.x=p.x;drone.position.z=p.z;drone.position.y=.35+visualAltitude/worldMetersPerUnit*4;shadow.position.set(p.x,.12,p.z);if(targetBeacon.visible&&d.target){const tp=worldPoint(d.target[0],d.target[1],d.home);targetBeacon.position.set(tp.x,.12,tp.z)}
   const spinning=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(s);rotors.forEach((r,i)=>{if(spinning)r.rotation.y+=(i%2?-.9:.9)*dt*18});
   if(spinning&&s==='ENROUTE'&&lastGPS){const dx=p.x-lastGPS.x,dz=p.z-lastGPS.z;if(Math.hypot(dx,dz)>.001)drone.rotation.y=Math.atan2(dx,dz)}
   lastGPS=p;
   if(s==='DELIVERING'&&!d.kit_dropped){kit.visible=true;kit.position.y=-.52;}
   if(d.kit_dropped&&!kitAnimating){kitAnimating=true;kitDropStart=performance.now();kit.visible=true;const tp=worldPoint(d.target[0],d.target[1],d.home);groundKit.visible=true;groundKit.position.set(tp.x,.18,tp.z)}
   if(kitAnimating){const f=Math.min(1,(performance.now()-kitDropStart)/900);kit.position.y=-.52-f*1.5;if(f>=1){kit.visible=false;kitAnimating=false}}
   if(s==='COMPLETED'){kit.visible=false;groundKit.visible=false;visualAltitude=0}
   if(['ENROUTE','HOVERING','DELIVERING','RTL'].includes(s)){const focus=new THREE.Vector3(p.x,Math.max(1.5,drone.position.y),p.z);controls.target.lerp(focus,.045)}
 }
 controls.update();renderer.render(scene,camera)}frame();
</script></body></html>'''
