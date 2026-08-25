"""Realistic 3D drone hardware/signal-flow presentation for VanniKawachh.

Uses the open-source AMV Lab drone GLB as the aircraft shell and overlays the
actual proposed onboard systems (battery/PDB, ESCs, flight controller,
GPS/compass, companion/LoRa, camera, servo/payload). The view is driven by the
same deployed /drone_state mission feed as the Wokwi -> hub pipeline.

The GLB is CC BY 4.0; attribution is shown in the UI.
"""
from fastapi.responses import HTMLResponse


def attach(app):
    @app.get("/drone-hardware", response_class=HTMLResponse)
    def drone_hardware_page():
        return HTML


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanniKawachh | Drone Hardware Simulation</title>
<style>
:root{--bg:#050b11;--panel:#08141d;--line:#29404e;--txt:#eaf5f8;--muted:#8da6b5;--power:#ffb34c;--data:#69b5ff;--ctrl:#35e2b3;--payload:#ff6875;--ok:#35e2b3;--warn:#ffb34c}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--txt);font:12px Inter,Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 430px;width:100vw;height:100vh}
#view{position:relative;min-width:0;min-height:0}#stage{display:block;width:100%;height:100%}
.top{position:absolute;z-index:10;left:12px;right:12px;top:12px;display:flex;justify-content:space-between;pointer-events:none}.pill{background:#06131ee6;border:1px solid var(--line);border-radius:999px;padding:8px 12px;color:var(--muted)}.pill b{color:#fff}
#side{background:#07121bf8;border-left:1px solid var(--line);padding:13px;overflow:auto}.title{font-size:21px;font-weight:900}.sub,.note{font-size:10px;color:var(--muted);line-height:1.5}.card{background:linear-gradient(180deg,#0e1f2a,#09151d);border:1px solid var(--line);border-radius:12px;padding:11px;margin:9px 0}.lab{font-size:10px;color:var(--muted);font-weight:800;letter-spacing:.1em}.big{font-size:27px;font-weight:900;margin-top:3px}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--payload)}.row{display:flex;justify-content:space-between;gap:8px;margin-top:7px}.val{font-weight:800;text-align:right}.power{color:var(--power)}.data{color:var(--data)}.ctrl{color:var(--ctrl)}.payload{color:var(--payload)}
.buttons{display:grid;grid-template-columns:1fr 1fr;gap:7px}.btn{border:1px solid var(--line);background:#112432;color:#fff;padding:10px;border-radius:8px;font-weight:800;cursor:pointer}.btn.primary{background:#0e2c24;border-color:#296d5a}.btn.warnBtn{background:#2a2113;border-color:#705126}.btn:hover{filter:brightness(1.12)}
.seq{display:grid;gap:4px}.step{padding:7px 9px;border:1px solid #1d3440;border-radius:8px;background:#09151d;color:#677e8b}.step.active{border-color:#8e6427;background:#211a10;color:#ffdda3;font-weight:800}.step.done{border-color:#286c5a;background:#0b211b;color:#adf4e0}
.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:3px;align-items:center}.node{padding:7px 3px;text-align:center;font-size:8px;border:1px solid #284354;border-radius:7px;background:#0a1922}.node.active{border-color:var(--ctrl);box-shadow:0 0 12px #35e2b325}.arr{color:var(--ctrl)}
.legend{display:grid;grid-template-columns:1fr 1fr;gap:6px}.legend div{padding:7px;border:1px solid var(--line);border-radius:7px;font-size:10px}.sw{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}.sp{background:var(--power)}.sd{background:var(--data)}.sc{background:var(--ctrl)}.sx{background:var(--payload)}
#log{height:80px;overflow:auto;background:#061018;border:1px solid #18313e;border-radius:7px;padding:6px;font:9px/1.45 ui-monospace,Consolas,monospace;color:#8fb9c7}
@media(max-width:900px){#app{grid-template-columns:1fr}#side{position:absolute;z-index:20;right:0;top:0;bottom:0;width:min(430px,95vw);box-shadow:-20px 0 40px #000b}}
</style>
</head>
<body>
<div id="app">
<section id="view">
<div class="top"><div class="pill"><b>VANNIKAWACHH</b> · 3D ON-BOARD HARDWARE</div><div class="pill">SOURCE: <b id="src">LIVE HUB</b></div></div>
<canvas id="stage"></canvas>
</section>
<aside id="side">
<div class="title">Drone Hardware + Signal Simulation</div>
<div class="sub">Uses an open-source GLB drone shell and overlays the proposed electronics so the evaluator can see how the aircraft is powered, controlled and actuated. Mission state comes from the deployed <b>/drone_state</b>.</div>
<div class="card"><div class="lab">LIVE SYSTEM</div><div id="state" class="big ok">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="val">—</span></div><div class="row"><span>GPS</span><span id="gps" class="val">—</span></div><div class="row"><span>Speed</span><span id="speed" class="val">0.0 m/s</span></div><div class="row"><span>Altitude</span><span id="alt" class="val">0.0 m</span></div></div>
<div class="card"><div class="lab">PROPULSION / POWER</div><div class="row"><span>LiPo battery</span><span id="battery" class="val power">POWER ON</span></div><div class="row"><span>PDB / regulator</span><span id="pdb" class="val power">FEEDING</span></div><div class="row"><span>ESCs</span><span id="escs" class="val">0 / 4 ACTIVE</span></div><div class="row"><span>BLDC motors</span><span id="motors" class="val">STOPPED</span></div><div class="row"><span>Propellers</span><span id="props" class="val">STOPPED</span></div></div>
<div class="card"><div class="lab">CONTROL / DATA</div><div class="row"><span>GPS + compass → FC</span><span id="gpsPath" class="val data">DATA</span></div><div class="row"><span>ESP32 / LoRa → companion</span><span id="linkPath" class="val data">STANDBY</span></div><div class="row"><span>Companion → FC</span><span id="fcPath" class="val ctrl">STANDBY</span></div><div class="row"><span>FC → ESC commands</span><span id="escPath" class="val ctrl">STANDBY</span></div><div class="row"><span>Payload servo</span><span id="servo" class="val">CLOSED</span></div><div class="row"><span>Health kit</span><span id="kit" class="val">SECURED</span></div></div>
<div class="card"><div class="lab">MISSION SEQUENCE</div><div class="seq"><div class="step" id="s1">○ Distress received</div><div class="step" id="s2">○ Companion / link active</div><div class="step" id="s3">○ Flight controller armed</div><div class="step" id="s4">○ ESC commands sent</div><div class="step" id="s5">○ Motors + propellers spinning</div><div class="step" id="s6">○ Navigate / hover</div><div class="step" id="s7">○ Payload servo opens</div><div class="step" id="s8">○ Health kit released</div><div class="step" id="s9">○ RTL / landing</div></div></div>
<div class="card"><div class="lab">SYSTEM SIGNAL CHAIN</div><div class="chain"><div class="node" id="n1">ESP32<br>SENSOR</div><div class="arr">→</div><div class="node" id="n2">COMPANION<br>+ LoRa</div><div class="arr">→</div><div class="node" id="n3">FLIGHT<br>CONTROLLER</div><div class="arr">→</div><div class="node" id="n4">ESCs +<br>SERVO</div></div></div>
<div class="card"><div class="lab">3D EXPLAINER</div><div class="row"><span>Model</span><span class="val">AMV Lab drone.glb</span></div><div class="row"><span>License</span><span class="val">CC BY 4.0</span></div><div class="row"><span>Parts mode</span><span class="val">overlay + explode</span></div><div class="note">The open-source aircraft shell is used as the visual airframe. Internal electronics are separate 3D components because a generic airframe GLB does not contain your proposed Pixhawk/ESC/LoRa/payload hardware.</div></div>
<div class="buttons"><button class="btn primary" id="live">LIVE HUB</button><button class="btn" id="trigger">TEST DISTRESS</button><button class="btn" id="explode">EXPLODED</button><button class="btn warnBtn" id="assemble">ASSEMBLED</button></div>
<div class="card"><div class="lab">EVENT LOG</div><div id="log"></div></div>
<div class="note">Open-source model credit: AMV Lab aircraft-models, CC BY 4.0. See the repository link in the page footer/source. This visual layer demonstrates the intended hardware integration; ArduPilot SITL remains the flight-physics validation.</div>
</aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

const $=id=>document.getElementById(id), log=m=>{const e=$('log');e.innerHTML+=`<div>${new Date().toLocaleTimeString()} · ${m}</div>`;e.scrollTop=e.scrollHeight};
const MODEL='https://cdn.jsdelivr.net/gh/amvlab/aircraft-models@main/models/drone_nologo.glb';
const FALLBACK='https://cdn.jsdelivr.net/gh/CesiumGS/cesium@main/Apps/SampleData/models/CesiumDrone/CesiumDrone.glb';
let live=true, last=null, lastMission=null,lastState='IDLE',timer=null,exploded=false,glb=null,glbParts=[],loadedName='';

const scene=new THREE.Scene();scene.background=new THREE.Color(0x050b11);scene.fog=new THREE.Fog(0x050b11,22,70);
const camera=new THREE.PerspectiveCamera(42,1,.1,220);camera.position.set(10,7.5,12);
const renderer=new THREE.WebGLRenderer({canvas:$('stage'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.target.set(0,1.5,0);
scene.add(new THREE.HemisphereLight(0x9bcfff,0x132029,2.2));const key=new THREE.DirectionalLight(0xffffff,3.2);key.position.set(8,14,8);key.castShadow=true;scene.add(key);
scene.add(new THREE.GridHelper(60,30,0x1b3b4b,0x102936));
const pad=new THREE.Mesh(new THREE.CylinderGeometry(3.2,.2,.12,64),new THREE.MeshBasicMaterial({color:0x102a35}));pad.position.y=.05;scene.add(pad);
const frame=new THREE.Group();frame.position.y=1.6;scene.add(frame);
const systemGroup=new THREE.Group();frame.add(systemGroup);
const overlayMat={fc:new THREE.MeshStandardMaterial({color:0x18414b,metalness:.2,roughness:.5}),gps:new THREE.MeshStandardMaterial({color:0x1d5d51,metalness:.15}),comp:new THREE.MeshStandardMaterial({color:0x315a75,metalness:.2}),battery:new THREE.MeshStandardMaterial({color:0xc67d24,metalness:.15}),esc:new THREE.MeshStandardMaterial({color:0x21434c}),servo:new THREE.MeshStandardMaterial({color:0xa73b42}),motor:new THREE.MeshStandardMaterial({color:0x222b31,metalness:.75,roughness:.3}),blade:new THREE.MeshStandardMaterial({color:0xb7c9d2,transparent:true,opacity:.72})};
const parts={};
function box(name,size,pos,mat){const m=new THREE.Mesh(new THREE.BoxGeometry(...size),mat);m.name=name;m.position.set(...pos);m.castShadow=true;systemGroup.add(m);parts[name]=m;return m}
function cyl(name,r,h,pos,mat){const m=new THREE.Mesh(new THREE.CylinderGeometry(r,r,h,24),mat);m.name=name;m.position.set(...pos);m.castShadow=true;systemGroup.add(m);parts[name]=m;return m}
parts.fc=box('FlightController',[.8,.16,.65],[0,.9,0],overlayMat.fc);parts.gps=box('GPSCompass',[.42,.12,.42],[0,1.35,0],overlayMat.gps);parts.batt=box('LiPoBattery',[1.3,.42,.8],[0,.45,0],overlayMat.battery);parts.comp=box('CompanionLoRa',[.72,.16,.56],[.85,.88,0],overlayMat.comp);parts.cam=box('Camera',[.34,.25,.3],[0,.72,.8],overlayMat.comp);parts.servo=box('PayloadServo',[.55,.18,.35],[0,.46,.84],overlayMat.servo);
const motorGroups=[],propGroups=[],escBoxes=[];const corners=[[-1.8,0,-1.05],[1.8,0,-1.05],[-1.8,0,1.05],[1.8,0,1.05]];
for(let i=0;i<4;i++){const [x,_,z]=corners[i];const esc=box('ESC'+(i+1),[.32,.16,.42],[x*.72,.83,z*.72],overlayMat.esc);escBoxes.push(esc);const mg=new THREE.Group();mg.position.set(x,.88,z);mg.name='Motor'+(i+1);const motor=new THREE.Mesh(new THREE.CylinderGeometry(.2,.2,.16,24),overlayMat.motor);motor.rotation.x=Math.PI/2;mg.add(motor);const pg=new THREE.Group();pg.position.y=.13;pg.name='Propeller'+(i+1);for(const ang of [0,Math.PI/2]){const b=new THREE.Mesh(new THREE.BoxGeometry(.9,.035,.08),overlayMat.blade);b.rotation.y=ang;pg.add(b)}mg.add(pg);systemGroup.add(mg);motorGroups.push(mg);propGroups.push(pg)}
const kit=box('HealthKit',[.46,.3,.4],[0,.12,.86],overlayMat.battery);kit.visible=false;

const signalMat=new THREE.MeshBasicMaterial({color:0x35e2b3});const powerMat=new THREE.MeshBasicMaterial({color:0xffb34c});const dataMat=new THREE.MeshBasicMaterial({color:0x69b5ff});
const pulseGroup=new THREE.Group();frame.add(pulseGroup);const pulses=[];
function pulse(a,b,mat){const g=new THREE.SphereGeometry(.065,12,12);const m=new THREE.Mesh(g,mat);pulseGroup.add(m);pulses.push({m,a,b,t:0});return m}
function updatePulses(dt,stage){pulses.forEach(p=>{p.t+=dt*(stage?1.8:0);const f=p.t%1;p.m.position.lerpVectors(p.a,p.b,f)})}
function addPulsePath(a,b,mat){return pulse(a,b,mat)}
function localPos(obj){const p=new THREE.Vector3();obj.getWorldPosition(p);return p}
const staticPaths=[
 ()=>[localPos(parts.batt),localPos(parts.fc),powerMat],
 ()=>[localPos(parts.comp),localPos(parts.fc),dataMat],
 ()=>[localPos(parts.gps),localPos(parts.fc),dataMat]
];

function resize(){const r=$('view').getBoundingClientRect();camera.aspect=r.width/r.height;camera.updateProjectionMatrix();renderer.setSize(r.width,r.height,false)}addEventListener('resize',resize);resize();

function apply3D(s,d){const fly=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(s);const armed=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(s);$('motors').textContent=armed?'RUNNING':'STOPPED';$('props').textContent=armed?'SPINNING':'STOPPED';$('escs').textContent=armed?'4 / 4 ACTIVE':'0 / 4 ACTIVE';$('gpsPath').textContent='LOCKED';$('linkPath').textContent=s==='IDLE'?'STANDBY':'ACTIVE';$('fcPath').textContent=armed?'COMMANDING':'STANDBY';$('escPath').textContent=armed?'PWM/DShot ACTIVE':'STANDBY';$('servo').textContent=s==='DELIVERING'?'OPEN':'CLOSED';$('kit').textContent=d?.kit_dropped?'DROPPED':'SECURED';
 ['n1','n2','n3','n4'].forEach(id=>$(id).classList.remove('active'));if(s!=='IDLE')$('n1').classList.add('active');if(s!=='IDLE')$('n2').classList.add('active');if(armed)$('n3').classList.add('active');if(['DELIVERING','RTL','COMPLETED'].includes(s))$('n4').classList.add('active');
 const q={s1:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s),s2:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s),s3:['ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s),s4:['ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s),s5:['ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'].includes(s),s6:['DELIVERING','RTL','COMPLETED'].includes(s),s7:['DELIVERING','RTL','COMPLETED'].includes(s),s8:d?.kit_dropped||['RTL','COMPLETED'].includes(s),s9:s==='RTL'||s==='COMPLETED'};
 Object.entries(q).forEach(([id,on])=>$(id).className=on?'step done':'step');const active={TAKEOFF:'s3',ENROUTE:'s5',HOVERING:'s6',DELIVERING:'s7',RTL:'s9'}[s];if(active)$(active).className='step active';
 const spin=armed;propGroups.forEach((p,i)=>p.rotation.y+=(i%2?-.85:.85)*spin*.9);motorGroups.forEach((m,i)=>m.rotation.y+=(i%2?.003:-.003)*spin);
 if(s==='DELIVERING'){parts.servo.material.emissive=new THREE.Color(0xff2a35);kit.visible=Boolean(d?.kit_dropped);kit.position.y=d?.kit_dropped?.12:.12}else{kit.visible=false;parts.servo.material.emissive=new THREE.Color(0x000000)}
 updatePulses(.016,spin);applyExplosion();
}
function applyExplosion(){const f=exploded?2.2:1;parts.fc.position.y=.9*f;parts.gps.position.y=1.35*f;parts.batt.position.y=.45/f;parts.comp.position.x=.85*f;parts.cam.position.z=.8*f;parts.servo.position.z=.84*f;escBoxes.forEach((e,i)=>{const [x,,z]=corners[i];e.position.set(x*.72*f,.83,z*.72*f)});motorGroups.forEach((m,i)=>{const [x,,z]=corners[i];m.position.set(x*f,.88*f,z*f)});kit.position.z=.86*f}
function loadGLB(url,onFail){const loader=new GLTFLoader();loader.load(url,g=>{if(glb)systemGroup.remove(glb);glb=g.scene;glb.name='AircraftGLB';glb.scale.setScalar(2.4);glb.position.set(0,.55,0);glb.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;glbParts.push(o.name)}});frame.add(glb);loadedName=url.includes('amvlab')?'AMV Lab drone_nologo.glb':'Fallback Cesium drone';log('Loaded GLB: '+loadedName);log('GLB parts: '+glbParts.slice(0,10).join(', ')+(glbParts.length>10?' …':''));},undefined,()=>{if(url!==FALLBACK){log('Primary GLB failed; loading fallback model');loadGLB(FALLBACK,onFail)}else{log('GLB load failed; using procedural hardware shell')}})}
loadGLB(MODEL);
for(const fn of staticPaths){setTimeout(()=>{try{const [a,b,m]=fn();addPulsePath(a,b,m)}catch{}} ,600)}

function applyState(d){if(!d)return;last=d;const s=d.state||'IDLE';$('state').textContent=s;$('state').className='big '+(s==='FAILED'?'bad':(['TAKEOFF','ENROUTE','RTL'].includes(s)?'warn':'ok'));$('mission').textContent=d.mission_id||'—';$('gps').textContent=d.lat!=null?Number(d.lat).toFixed(5)+', '+Number(d.lon).toFixed(5):'—';$('speed').textContent=(d.speed_ms!=null?Number(d.speed_ms):0).toFixed(1)+' m/s';$('alt').textContent=(d.altitude_m!=null?Number(d.altitude_m):(['ENROUTE','HOVERING','DELIVERING','RTL'].includes(s)?15:s==='TAKEOFF'?5:0)).toFixed(1)+' m';if(d.mission_id!==lastMission){lastMission=d.mission_id;if(d.mission_id)log('MISSION '+d.mission_id)}if(s!==lastState){lastState=s;log('STATE → '+s)}apply3D(s,d)}
async function poll(){if(!live)return;try{const r=await fetch('/drone_state',{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);applyState(await r.json());$('src').textContent='LIVE HUB'}catch(e){$('src').textContent='HUB ERROR';log('Hub read failed: '+e.message)}timer=setTimeout(poll,300)}
$('live').onclick=()=>{live=true;$('src').textContent='LIVE HUB';log('Live hub enabled');poll()};
$('explode').onclick=()=>{exploded=true;applyExplosion();log('Exploded component view')};
$('assemble').onclick=()=>{exploded=false;applyExplosion();log('Assembled component view')};
$('trigger').onclick=async()=>{try{const lat=21.128,lon=79.047;log('TEST DISTRESS → /node-alert');const r=await fetch(`/node-alert?node=DRONE-HARDWARE&lat=${lat}&lon=${lon}&event=1&conf=0.99&pir=1&light=30`,{method:'POST'});if(!r.ok)throw new Error('HTTP '+r.status);log('Hub: '+JSON.stringify(await r.json()));live=true;poll()}catch(e){log('Trigger failed: '+e.message)}};
log('Hardware view ready');poll();
const clock=new THREE.Clock();function frameLoop(){requestAnimationFrame(frameLoop);const dt=Math.min(clock.getDelta(),.05);controls.update();renderer.render(scene,camera)}frameLoop();
</script>
</body></html>'''
'''
