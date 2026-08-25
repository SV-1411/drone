"""Browser 3D hardware simulation layer for VanniKawachh.

This is intentionally a visualization layer, not a replacement for ArduPilot SITL.
It consumes the same deployed /drone_state feed produced by hub/sim_drone.py.
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
<title>VanniKawachh | 3D Drone Hardware Simulation</title>
<style>
:root{--bg:#050b11;--panel:#09141d;--panel2:#0d1d28;--line:#203747;--text:#eaf3f8;--muted:#8da4b4;--cyan:#32e0b0;--amber:#ffb24a;--red:#ff5f6d;--blue:#69adff}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 390px;width:100vw;height:100vh}
#view{position:relative;min-width:0;min-height:0}#stage{width:100%;height:100%;display:block}
.hud{position:absolute;z-index:4;left:16px;right:16px;top:14px;display:flex;justify-content:space-between;pointer-events:none}.pill{background:#07131de8;border:1px solid var(--line);border-radius:999px;padding:8px 13px;font-size:12px;color:var(--muted);backdrop-filter:blur(8px)}.pill b{color:var(--text)}
#side{background:#07121bf7;border-left:1px solid var(--line);padding:14px;overflow:auto}.title{font-size:19px;font-weight:850}.sub{font-size:11px;color:var(--muted);line-height:1.45;margin-top:3px}.card{background:linear-gradient(180deg,#0d1c27,#09151e);border:1px solid var(--line);border-radius:13px;padding:11px;margin:10px 0}.label{font-size:10px;color:var(--muted);letter-spacing:.1em}.state{font-size:24px;font-weight:900;margin-top:4px}.live{color:var(--cyan)}.warn{color:var(--amber)}.bad{color:var(--red)}.row{display:flex;justify-content:space-between;gap:10px;margin-top:7px;font-size:12px}.value{font-weight:750;text-align:right}.ok{color:var(--cyan)}
.buttons{display:grid;grid-template-columns:1fr 1fr;gap:7px}.buttons button{border:1px solid var(--line);border-radius:9px;padding:11px 8px;background:#122432;color:var(--text);font-weight:800;cursor:pointer}.buttons button:hover{background:#19374b}.buttons .primary{border-color:#276b5b;background:#0f2b24}.buttons .warn{border-color:#705327;background:#2a2113}.buttons .danger{border-color:#71333b;background:#2a1217}
.sequence{font-size:11px;line-height:1.55}.sequence div{padding:2px 0;color:#617786}.sequence .done{color:var(--cyan)}.sequence .active{color:var(--amber);font-weight:800}.flow{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:4px;align-items:center;text-align:center;font-size:8px}.node{padding:7px 3px;border:1px solid var(--line);border-radius:8px;background:#0c1a24;color:#a7bdca}.arrow{color:var(--cyan)}#log{height:120px;overflow:auto;background:#061019;border:1px solid #142734;border-radius:8px;padding:7px;font:10px/1.5 ui-monospace,Consolas,monospace;color:#8fb9cc}.foot{font-size:9px;color:#647b89;line-height:1.45;margin-top:8px}
@media(max-width:850px){#app{grid-template-columns:1fr}#side{position:absolute;right:0;top:0;bottom:0;width:min(390px,94vw);box-shadow:-15px 0 35px #000b}}
</style>
</head>
<body>
<div id="app">
<section id="view">
 <div class="hud"><div class="pill"><b>VANNIKAWACHH</b> · 3D DRONE HARDWARE SIM</div><div class="pill">SOURCE: <b id="source">LIVE HUB</b></div></div>
 <canvas id="stage"></canvas>
</section>
<aside id="side">
 <div><div class="title">Virtual Drone Unit</div><div class="sub">This page is deployed inside the VanniKawachh hub. It consumes the same mission state generated when the Wokwi/ESP32 node calls <b>/node-alert</b>.</div></div>
 <div class="card"><div class="label">FLIGHT STATE</div><div id="state" class="state live">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="value">—</span></div><div class="row"><span>Altitude</span><span id="alt" class="value">0.0 m</span></div><div class="row"><span>Speed</span><span id="speed" class="value">0.0 m/s</span></div></div>
 <div class="card"><div class="label">NAVIGATION</div><div class="row"><span>Home</span><span id="home" class="value">—</span></div><div class="row"><span>Target</span><span id="target" class="value">—</span></div><div class="row"><span>Position</span><span id="pos" class="value">—</span></div></div>
 <div class="card"><div class="label">VIRTUAL HARDWARE</div><div class="row"><span>4 × BLDC / ESC</span><span id="rotors" class="value ok">OFF</span></div><div class="row"><span>Flight controller</span><span class="value ok">CONNECTED</span></div><div class="row"><span>GPS + compass</span><span class="value ok">LOCKED</span></div><div class="row"><span>Companion / link</span><span class="value ok">ONLINE</span></div><div class="row"><span>Payload servo</span><span id="servo" class="value">CLOSED</span></div><div class="row"><span>Health kit</span><span id="kit" class="value">SECURED</span></div></div>
 <div class="card"><div class="label">SIGNAL / HARDWARE CHAIN</div><div class="flow"><div class="node">ESP32<br>NODE</div><div class="arrow">→</div><div class="node">HUB<br>DISPATCH</div><div class="arrow">→</div><div class="node">FLIGHT<br>CONTROLLER</div><div class="arrow">→</div><div class="node">MOTORS<br>+ PAYLOAD</div></div></div>
 <div class="card"><div class="label">MISSION SEQUENCE</div><div class="sequence"><div id="q1">○ Distress trigger</div><div id="q2">○ Arm / spin rotors</div><div id="q3">○ Takeoff</div><div id="q4">○ Fly to distress GPS</div><div id="q5">○ Hover at location</div><div id="q6">○ Open payload bay</div><div id="q7">○ Drop health kit</div><div id="q8">○ RTL / land</div></div></div>
 <div class="buttons"><button id="live" class="primary">LIVE HUB</button><button id="trigger">TRIGGER HUB</button><button id="demo">RUN LOCAL DEMO</button><button id="reset" class="warn">RESET VIEW</button></div>
 <div class="card"><div class="label">EVENT LOG</div><div id="log"></div></div>
 <div class="foot">LIVE HUB polls <b>/drone_state</b>. TRIGGER HUB calls this deployed hub's own <b>/node-alert</b> endpoint. RUN LOCAL DEMO is only a visual fallback. The 3D layer is not flight physics; ArduPilot SITL remains the flight-physics proof.</div>
</aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const $=id=>document.getElementById(id); const log=m=>{const e=$('log');e.innerHTML+=`<div>${new Date().toLocaleTimeString()} · ${m}</div>`;e.scrollTop=e.scrollHeight};
const homeFallback=[21.12330,79.04194], targetFallback=[21.12800,79.04700];
let mode='live', live=true, demoTimer=null, lastMission=null, lastState='IDLE', lastData=null;

const scene=new THREE.Scene(); scene.background=new THREE.Color(0x061018); scene.fog=new THREE.Fog(0x061018,35,105);
const camera=new THREE.PerspectiveCamera(45,1,.1,300); camera.position.set(11,8,14);
const renderer=new THREE.WebGLRenderer({canvas:$('stage'),antialias:true}); renderer.setPixelRatio(Math.min(devicePixelRatio,2)); renderer.shadowMap.enabled=true;
const controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true; controls.target.set(0,2,0);
scene.add(new THREE.HemisphereLight(0x9bcfff,0x14202a,2.2)); const key=new THREE.DirectionalLight(0xffffff,3); key.position.set(8,14,8); key.castShadow=true; scene.add(key);
const grid=new THREE.GridHelper(90,45,0x1b3b4b,0x102936); scene.add(grid);
const pad=new THREE.Mesh(new THREE.CylinderGeometry(3.2,.2,0.12,64),new THREE.MeshBasicMaterial({color:0x102a35}));pad.position.y=.05;scene.add(pad);
const ring=new THREE.Mesh(new THREE.TorusGeometry(3.2,.025,8,96),new THREE.MeshBasicMaterial({color:0x2ee0b0}));ring.rotation.x=Math.PI/2;ring.position.y=.13;scene.add(ring);

const drone=new THREE.Group(); scene.add(drone); drone.position.set(0,0.9,0);
const body=new THREE.Mesh(new THREE.BoxGeometry(1.7,.28,1.05),new THREE.MeshStandardMaterial({color:0x1d2d36,metalness:.65,roughness:.3}));body.castShadow=true;drone.add(body);
const top=new THREE.Mesh(new THREE.BoxGeometry(.9,.18,.65),new THREE.MeshStandardMaterial({color:0x32e0b0,metalness:.3,roughness:.35}));top.position.y=.22;drone.add(top);
const cam=new THREE.Mesh(new THREE.BoxGeometry(.28,.22,.28),new THREE.MeshStandardMaterial({color:0x101820,metalness:.5}));cam.position.set(0,-.05,.58);drone.add(cam);
const arms=[]; const rotors=[]; const rotorCenters=[[-1.35,.12,-.78],[1.35,.12,-.78],[-1.35,.12,.78],[1.35,.12,.78]];
for(const [x,y,z] of rotorCenters){const arm=new THREE.Mesh(new THREE.BoxGeometry(1.9,.1,.12),new THREE.MeshStandardMaterial({color:0x607681,metalness:.6}));arm.position.set(x/2,.02,z/2);arm.rotation.y=Math.atan2(z,x);drone.add(arm);arms.push(arm);const g=new THREE.Group();g.position.set(x,y,z);const motor=new THREE.Mesh(new THREE.CylinderGeometry(.16,.16,.12,24),new THREE.MeshStandardMaterial({color:0x222b31,metalness:.8}));motor.rotation.x=Math.PI/2;g.add(motor);for(const a of [0,Math.PI/2]){const p=new THREE.Mesh(new THREE.BoxGeometry(.85,.035,.09),new THREE.MeshBasicMaterial({color:0x63a8ff,transparent:true,opacity:.62}));p.rotation.y=a;g.add(p)}drone.add(g);rotors.push(g)}
const bay=new THREE.Mesh(new THREE.BoxGeometry(.7,.18,.55),new THREE.MeshStandardMaterial({color:0x303b42,metalness:.4}));bay.position.set(0,-.25,0);drone.add(bay);
const kit=new THREE.Mesh(new THREE.BoxGeometry(.42,.3,.42),new THREE.MeshStandardMaterial({color:0xffb24a,metalness:.1}));kit.position.set(0,-.52,0);kit.visible=false;drone.add(kit);
const shadow=new THREE.Mesh(new THREE.CircleGeometry(1.5,48),new THREE.MeshBasicMaterial({color:0x000000,transparent:true,opacity:.25}));shadow.rotation.x=-Math.PI/2;scene.add(shadow);

function resize(){const r=$('stage').getBoundingClientRect();camera.aspect=r.width/r.height;camera.updateProjectionMatrix();renderer.setSize(r.width,r.height,false)}addEventListener('resize',resize);resize();
function setText(id,v){$(id).textContent=v}
function fmtCoord(v){return Array.isArray(v)?v.map(x=>Number(x).toFixed(5)).join(', '):'—'}
function stateClass(s){return ['DELIVERING','HOVERING'].includes(s)?'warn':(['COMPLETED','IDLE'].includes(s)?'live':'bad'&&s==='FAILED'?'bad':'live')}
function apply(d){
 if(!d)return; lastData=d; const s=d.state||'IDLE';
 setText('state',s); $('state').className='state '+(s==='FAILED'?'bad':(['TAKEOFF','ENROUTE','RTL','DISPATCHED'].includes(s)?'warn':'live'));
 setText('mission',d.mission_id||'—'); setText('home',fmtCoord(d.home)); setText('target',fmtCoord(d.target)); setText('pos',d.lat!=null?Number(d.lat).toFixed(5)+', '+Number(d.lon).toFixed(5):'—');
 const flying=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','DISPATCHED'].includes(s); setText('rotors',flying?'SPINNING':'OFF');setText('servo',s==='DELIVERING'?'OPEN':'CLOSED');setText('kit',d.kit_dropped?'DROPPED':'SECURED');
 const alt=s==='TAKEOFF'?5:(['ENROUTE','HOVERING','DELIVERING','RTL'].includes(s)?15:0); setText('alt',alt.toFixed(1)+' m');
 const speed=s==='ENROUTE'||s==='RTL'?8:(s==='TAKEOFF'?3:0);setText('speed',speed.toFixed(1)+' m/s');
 const q={q1:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s),q2:flying,q3:['ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s),q4:['HOVERING','DELIVERING','RTL','COMPLETED'].includes(s),q5:['DELIVERING','RTL','COMPLETED'].includes(s),q6:['DELIVERING','RTL','COMPLETED'].includes(s),q7:d.kit_dropped||['RTL','COMPLETED'].includes(s),q8:s==='RTL'||s==='COMPLETED'};
 Object.entries(q).forEach(([id,on])=>$(id).className=on?'done':(id==='q1'&&s==='TAKEOFF'?'active':''));
 if(d.mission_id!==lastMission){lastMission=d.mission_id;if(d.mission_id)log('Mission '+d.mission_id+' · '+s)}
 if(s!==lastState){log('Flight state → '+s);lastState=s}
}
function positionFromGPS(d){if(d?.lat==null||d?.lon==null)return null;const h=d.home||homeFallback;const latScale=111000;const lonScale=111000*Math.cos((h[0]*Math.PI)/180);return new THREE.Vector3((d.lon-h[1])*lonScale/9,0,(d.lat-h[0])*latScale/9)}
function animateVisual(d,dt){const s=d?.state||'IDLE';const p=positionFromGPS(d);if(p){const altitude=['ENROUTE','HOVERING','DELIVERING','RTL'].includes(s)?3.0:(s==='TAKEOFF'?1.4:0.7);drone.position.x=p.x;drone.position.z=-p.z;drone.position.y=altitude;shadow.position.set(drone.position.x,.12,drone.position.z)}else{drone.position.y=.8;shadow.position.set(drone.position.x,.12,drone.position.z)}const spin=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(s);rotors.forEach((r,i)=>{if(spin)r.rotation.y+=(i%2?-.65:.65)*dt*18});if(s==='DELIVERING'){bay.material.color.set(0xffb24a);kit.visible=!d.kit_dropped;kit.position.y=-.52-(d.kit_dropped?1.4:0)}else{bay.material.color.set(0x303b42);kit.visible=false}drone.rotation.z=(s==='ENROUTE'?-0.05:s==='RTL'?0.05:0);}
async function poll(){if(!live)return;try{const r=await fetch('/drone_state',{cache:'no-store'});if(r.ok)apply(await r.json())}catch(e){$('source').textContent='HUB UNREACHABLE'}setTimeout(poll,350)}
function localDemo(){live=false;$('source').textContent='LOCAL DEMO';let start=performance.now();const H=homeFallback,T=targetFallback;function tick(){const t=(performance.now()-start)/1000;let d={state:'IDLE',mission_id:'local-demo',home:H,target:T,lat:H[0],lon:H[1],kit_dropped:false};if(t>1)d.state='TAKEOFF';if(t>3){d.state='ENROUTE';const f=Math.min(1,(t-3)/6);d.lat=H[0]+(T[0]-H[0])*f;d.lon=H[1]+(T[1]-H[1])*f}if(t>9)d.state='HOVERING',d.lat=T[0],d.lon=T[1];if(t>11)d.state='DELIVERING',d.lat=T[0],d.lon=T[1];if(t>13)d.kit_dropped=true;if(t>15){d.state='RTL';const f=Math.min(1,(t-15)/6);d.lat=T[0]+(H[0]-T[0])*f;d.lon=T[1]+(H[1]-T[1])*f}if(t>21)d.state='COMPLETED',d.lat=H[0],d.lon=H[1];apply(d);if(t<23)demoTimer=requestAnimationFrame(tick);else log('Local demo complete')}cancelAnimationFrame(demoTimer);demoTimer=requestAnimationFrame(tick)}
$('live').onclick=()=>{cancelAnimationFrame(demoTimer);live=true;mode='live';$('source').textContent='LIVE HUB';log('Connected to deployed hub');poll()};
$('demo').onclick=()=>{log('Starting local visual demo');localDemo()};
$('reset').onclick=()=>{cancelAnimationFrame(demoTimer);live=true;lastMission=null;lastState='IDLE';apply({state:'IDLE',home:homeFallback,lat:homeFallback[0],lon:homeFallback[1],target:null,kit_dropped:false});log('View reset');poll()};
$('trigger').onclick=async()=>{try{const la=targetFallback[0],lo=targetFallback[1];log('Sending TEST distress to /node-alert');const r=await fetch(`/node-alert?node=3D-SIM&lat=${la}&lon=${lo}&event=1&conf=0.99&pir=1&light=30`,{method:'POST'});const j=await r.json();log(j.dispatched?'Hub dispatched '+j.mission_id:'Hub response: '+JSON.stringify(j));live=true;$('source').textContent='LIVE HUB';poll()}catch(e){log('Hub trigger failed: '+e.message)}};
log('3D layer ready · waiting for /drone_state');poll();
let clock=new THREE.Clock();function frame(){requestAnimationFrame(frame);const dt=Math.min(clock.getDelta(),.05);controls.update();animateVisual(lastData,dt);renderer.render(scene,camera)}frame();
</script></body></html>'''
