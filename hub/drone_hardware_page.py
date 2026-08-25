"""3D onboard drone hardware / signal-flow visualization for VanniKawachh.

This is a presentation-facing hardware architecture view. It consumes the same
live /drone_state mission feed as the existing deployed demo, but visualizes the
physical onboard chain separately:

Battery/PDB -> ESCs -> BLDC motors -> propellers
GPS/compass + IMU -> flight controller -> ESC control outputs
Companion/LoRa -> flight controller mission commands
Flight controller/companion -> payload servo -> health kit
Camera -> companion/ground side evidence

It is a visualization of the proposed integration, not a substitute for real
motor electronics or ArduPilot physics.
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
<title>VanniKawachh | Drone Hardware & Signal Simulation</title>
<style>
:root{--bg:#040a0f;--panel:#08131c;--panel2:#0c1b25;--line:#23404e;--txt:#edf7fa;--muted:#8da6b4;--power:#ffb34c;--data:#63b5ff;--control:#32e0b0;--warn:#ff7c7c;--metal:#7d919b;--body:#1a2830}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--txt);font:12px Inter,Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 430px;width:100vw;height:100vh}
#view{position:relative;min-width:0;min-height:0}#stage{width:100%;height:100%;display:block}
.top{position:absolute;z-index:10;top:12px;left:12px;right:12px;display:flex;justify-content:space-between;pointer-events:none}.pill{background:#06131ce8;border:1px solid var(--line);border-radius:999px;padding:8px 12px;color:var(--muted)}.pill b{color:#fff}
#side{overflow:auto;background:#07121bf8;border-left:1px solid var(--line);padding:13px}.title{font-size:21px;font-weight:900}.sub,.note{color:var(--muted);font-size:10px;line-height:1.5}.card{background:linear-gradient(180deg,#0d1d27,#08131c);border:1px solid var(--line);border-radius:12px;padding:11px;margin:9px 0}.lab{font-size:10px;letter-spacing:.1em;color:var(--muted);font-weight:800}.big{font-size:26px;font-weight:900;margin:3px 0}.row{display:flex;justify-content:space-between;gap:8px;margin:7px 0}.val{font-weight:800;text-align:right}.power{color:var(--power)}.data{color:var(--data)}.control{color:var(--control)}.warn{color:var(--warn)}
.buttons{display:grid;grid-template-columns:1fr 1fr;gap:7px}.btn{border:1px solid var(--line);border-radius:8px;padding:10px;background:#112432;color:#fff;font-weight:800;cursor:pointer}.btn.primary{background:#0d2c24;border-color:#276b5c}.btn:hover{filter:brightness(1.12)}
.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:3px;align-items:center}.node{padding:7px 3px;text-align:center;font-size:8px;border:1px solid #2a4553;border-radius:7px;background:#0a1922}.arr{color:var(--control)}.node.active{border-color:var(--control);box-shadow:0 0 12px #32e0b033}
.legend{display:grid;grid-template-columns:1fr 1fr;gap:6px}.legend div{border:1px solid var(--line);border-radius:7px;padding:7px;font-size:10px}.sw{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}.spow{background:var(--power)}.sdata{background:var(--data)}.sctrl{background:var(--control)}
.seq{display:grid;gap:4px}.step{padding:7px 9px;border:1px solid #1d3440;border-radius:8px;color:#687f8b;background:#09151d}.step.active{border-color:#916628;background:#221a10;color:#ffdfa6;font-weight:800}.step.done{border-color:#296d5b;background:#0c211b;color:#aef4e1}
#log{height:95px;overflow:auto;background:#051017;border:1px solid #17303d;border-radius:7px;padding:6px;font:9px/1.45 ui-monospace,Consolas,monospace;color:#8fb9c7}
@media(max-width:900px){#app{grid-template-columns:1fr}#side{position:absolute;z-index:20;right:0;top:0;bottom:0;width:min(430px,95vw);box-shadow:-20px 0 40px #000b}}
</style>
</head>
<body>
<div id="app">
<section id="view"><div class="top"><div class="pill"><b>VANNIKAWACHH</b> · ON-BOARD HARDWARE + SIGNAL FLOW</div><div class="pill">SOURCE: <b id="source">LIVE HUB</b></div></div><canvas id="stage"></canvas></section>
<aside id="side">
<div class="title">Drone Hardware Simulation</div>
<div class="sub">A 3D exploded view of the proposed aircraft. The same live mission state drives the rotor system, flight-controller chain, payload actuator and signal animation.</div>
<div class="card"><div class="lab">MISSION / SYSTEM STATE</div><div id="state" class="big control">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="val">—</span></div><div class="row"><span>GPS</span><span id="gps" class="val">—</span></div><div class="row"><span>Speed</span><span id="speed" class="val">0.0 m/s</span></div><div class="row"><span>Altitude</span><span id="alt" class="val">0.0 m</span></div></div>
<div class="card"><div class="lab">PHYSICAL POWER PATH</div><div class="row"><span>LiPo battery</span><span id="battery" class="val power">POWER ON</span></div><div class="row"><span>PDB / regulator</span><span id="pdb" class="val power">FEEDING ESCs</span></div><div class="row"><span>ESC outputs</span><span id="escs" class="val">0 / 4 ACTIVE</span></div><div class="row"><span>BLDC motors</span><span id="motors" class="val">STOPPED</span></div><div class="row"><span>Propellers</span><span id="props" class="val">STOPPED</span></div></div>
<div class="card"><div class="lab">CONTROL / DATA PATH</div><div class="row"><span>GPS + compass → FC</span><span id="gpsPath" class="val data">DATA</span></div><div class="row"><span>ESP32/LoRa → companion</span><span id="linkPath" class="val data">STANDBY</span></div><div class="row"><span>Companion → FC</span><span id="fcPath" class="val control">STANDBY</span></div><div class="row"><span>FC → ESC signal</span><span id="escPath" class="val control">STANDBY</span></div><div class="row"><span>Servo command</span><span id="servo" class="val">CLOSED</span></div></div>
<div class="card"><div class="lab">MISSION SEQUENCE</div><div class="seq"><div class="step" id="s1">○ Distress received</div><div class="step" id="s2">○ Companion / link active</div><div class="step" id="s3">○ FC armed</div><div class="step" id="s4">○ ESCs commanded</div><div class="step" id="s5">○ Motors + props spinning</div><div class="step" id="s6">○ Navigate / hover</div><div class="step" id="s7">○ Payload servo open</div><div class="step" id="s8">○ Health kit released</div><div class="step" id="s9">○ RTL / landing</div></div></div>
<div class="card"><div class="lab">CONNECTION LEGEND</div><div class="legend"><div><span class="sw spow"></span>Power</div><div><span class="sw sdata"></span>Sensor / data</div><div><span class="sw sctrl"></span>Control command</div><div><span class="sw" style="background:#ff7c7c"></span>Payload actuation</div></div></div>
<div class="card"><div class="lab">SYSTEM SIGNAL CHAIN</div><div class="chain"><div class="node" id="n1">ESP32<br>SENSOR</div><div class="arr">→</div><div class="node" id="n2">COMPANION<br>+ LoRa</div><div class="arr">→</div><div class="node" id="n3">FLIGHT<br>CONTROLLER</div><div class="arr">→</div><div class="node" id="n4">ESCs +<br>SERVO</div></div></div>
<div class="buttons"><button class="btn primary" id="live">LIVE HUB</button><button class="btn" id="trigger">TEST DISTRESS</button><button class="btn" id="explode">EXPLODED VIEW</button><button class="btn" id="assemble">ASSEMBLED VIEW</button></div>
<div class="card"><div class="lab">EVENT LOG</div><div id="log"></div></div>
<div class="note">The 3D signal paths are an explanatory hardware simulation. They show the intended electrical/control architecture. The actual flight controller and aerodynamic physics remain validated separately with ArduPilot SITL.</div>
</aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const $=id=>document.getElementById(id);
const log=m=>{const e=$('log');e.innerHTML+=`<div>${new Date().toLocaleTimeString()} · ${m}</div>`;e.scrollTop=e.scrollHeight};
let live=true,last=null,lastState='IDLE',pollTimer=null,explodeMode=false;

const scene=new THREE.Scene();scene.background=new THREE.Color(0x050b11);scene.fog=new THREE.Fog(0x050b11,18,60);
const camera=new THREE.PerspectiveCamera(42,1,.1,200);camera.position.set(10,8,13);
const renderer=new THREE.WebGLRenderer({canvas:$('stage'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.target.set(0,1.5,0);
scene.add(new THREE.HemisphereLight(0xa8d7ff,0x182027,2.1));const key=new THREE.DirectionalLight(0xffffff,3.2);key.position.set(9,14,8);key.castShadow=true;scene.add(key);
scene.add(new THREE.GridHelper(55,28,0x193544,0x0e2630));
const base=new THREE.Mesh(new THREE.CylinderGeometry(3.4,.2,.12,64),new THREE.MeshBasicMaterial({color:0x0d2731}));base.position.y=.05;scene.add(base);

const aircraft=new THREE.Group();scene.add(aircraft);aircraft.position.y=2.2;
const frame=new THREE.Group();aircraft.add(frame);
const darkMat=new THREE.MeshStandardMaterial({color:0x202e35,metalness:.55,roughness:.35});
const carbonMat=new THREE.MeshStandardMaterial({color:0x0d1418,metalness:.3,roughness:.45});
const pcbMat=new THREE.MeshStandardMaterial({color:0x183d45,metalness:.1,roughness:.55});
const orangeMat=new THREE.MeshStandardMaterial({color:0xd88c2b,metalness:.15,roughness:.45});
const blueMat=new THREE.MeshStandardMaterial({color:0x325c77,metalness:.2,roughness:.4});
const redMat=new THREE.MeshStandardMaterial({color:0x8a3034,metalness:.15,roughness:.45});

const body=new THREE.Mesh(new THREE.BoxGeometry(2.5,.35,1.55),carbonMat);body.castShadow=true;frame.add(body);
const topPlate=new THREE.Mesh(new THREE.BoxGeometry(1.65,.16,1.15),darkMat);topPlate.position.y=.28;frame.add(topPlate);
const fc=new THREE.Mesh(new THREE.BoxGeometry(.75,.14,.68),pcbMat);fc.position.set(0,.5,0);frame.add(fc);
const gps=new THREE.Mesh(new THREE.BoxGeometry(.46,.1,.46),pcbMat);gps.position.set(0,.86,0);frame.add(gps);
const compass=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,.06,24),orangeMat);compass.position.set(0,.95,0);frame.add(compass);
const battery=new THREE.Mesh(new THREE.BoxGeometry(1.2,.42,.78),orangeMat);battery.position.set(0,-.44,0);frame.add(battery);
const companion=new THREE.Mesh(new THREE.BoxGeometry(.72,.16,.58),blueMat);companion.position.set(.9,.34,0);frame.add(companion);
const cameraModule=new THREE.Mesh(new THREE.BoxGeometry(.34,.28,.34),blueMat);cameraModule.position.set(0,-.08,.9);frame.add(cameraModule);
const payloadBay=new THREE.Mesh(new THREE.BoxGeometry(.8,.22,.62),redMat);payloadBay.position.set(0,-.36,.94);frame.add(payloadBay);
const payloadDoor=new THREE.Mesh(new THREE.BoxGeometry(.82,.06,.65),darkMat);payloadDoor.position.set(0,-.51,.94);frame.add(payloadDoor);
const kit=new THREE.Mesh(new THREE.BoxGeometry(.46,.28,.42),orangeMat);kit.position.set(0,-.72,.94);kit.visible=false;frame.add(kit);

const motors=[],props=[],escs=[],wires=[];
const corners=[[-1.8,.0,-1.0],[1.8,.0,-1.0],[-1.8,.0,1.0],[1.8,.0,1.0]];
for(let i=0;i<4;i++){
 const [x,y,z]=corners[i];
 const arm=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,2.0,16),darkMat);arm.rotation.z=Math.PI/2;arm.position.set(x/2,.04,z/2);arm.rotation.y=Math.atan2(z,x);frame.add(arm);
 const esc=new THREE.Mesh(new THREE.BoxGeometry(.32,.16,.45),pcbMat);esc.position.set(x*.72,-.02,z*.72);frame.add(esc);escs.push(esc);
 const m=new THREE.Group();m.position.set(x,.05,z);const motor=new THREE.Mesh(new THREE.CylinderGeometry(.18,.18,.16,24),darkMat);motor.rotation.x=Math.PI/2;m.add(motor);
 const p=new THREE.Group();for(const ang of [0,Math.PI/2]){const blade=new THREE.Mesh(new THREE.BoxGeometry(.78,.035,.09),new THREE.MeshStandardMaterial({color:0x9bb5c0,transparent:true,opacity:.78,metalness:.1,roughness:.55}));blade.rotation.y=ang;p.add(blade)}p.position.y=.13;m.add(p);frame.add(m);motors.push(m);props.push(p);
 const line=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0x32e0b0,transparent:true,opacity:.65}));frame.add(line);wires.push({line,from:fc,to:esc});
}
const pwrLine=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0xffb34c,transparent:true,opacity:.8}));frame.add(pwrLine);
const dataLine=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0x63b5ff,transparent:true,opacity:.8}));frame.add(dataLine);
const ctrlLine=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0x32e0b0,transparent:true,opacity:.8}));frame.add(ctrlLine);
const payloadLine=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0xff7c7c,transparent:true,opacity:.8}));frame.add(payloadLine);
function putLine(line,pts){line.geometry.setFromPoints(pts)}

const pulses=[];
function pulse(path,color){const g=new THREE.Mesh(new THREE.SphereGeometry(.09,12,12),new THREE.MeshBasicMaterial({color}));scene.add(g);pulses.push({g,path,t:0})}
function path(a,b){return [a.clone(),b.clone()]}

function positions(){return {
 batt:battery.getWorldPosition(new THREE.Vector3()),pdb:new THREE.Vector3(0,2.0,0),
 fc:fc.getWorldPosition(new THREE.Vector3()),gps:gps.getWorldPosition(new THREE.Vector3()),comp:companion.getWorldPosition(new THREE.Vector3()),cam:cameraModule.getWorldPosition(new THREE.Vector3()),pay:payloadBay.getWorldPosition(new THREE.Vector3()),door:payloadDoor.getWorldPosition(new THREE.Vector3()),
 esc:escs.map(e=>e.getWorldPosition(new THREE.Vector3())),mot:motors.map(m=>m.getWorldPosition(new THREE.Vector3()))};}
function rebuildLines(){const p=positions();putLine(pwrLine,[p.batt,p.fc]);putLine(dataLine,[p.gps,p.fc]);putLine(ctrlLine,[p.comp,p.fc]);putLine(payloadLine,[p.fc,p.door]);wires.forEach((w,i)=>putLine(w.line,[p.fc,p.esc[i]]));}
rebuildLines();

function resize(){const r=document.getElementById('view').getBoundingClientRect();camera.aspect=r.width/r.height;camera.updateProjectionMatrix();renderer.setSize(r.width,r.height,false)}addEventListener('resize',resize);resize();
function setText(id,v){$(id).textContent=v}
function apply(d){last=d;if(!d)return;const s=d.state||'IDLE';setText('state',s);$('state').className='big '+(['TAKEOFF','ENROUTE','RTL'].includes(s)?'warn':'control');setText('mission',d.mission_id||'—');setText('gps',d.lat!=null?`${Number(d.lat).toFixed(5)}, ${Number(d.lon).toFixed(5)}`:'—');setText('speed',([ 'ENROUTE','RTL' ].includes(s)?'15.0 m/s':'0.0 m/s'));setText('alt',(['ENROUTE','HOVERING','DELIVERING','RTL'].includes(s)?'15.0 m':s==='TAKEOFF'?'5.0 m':'0.0 m'));
 const flying=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(s);setText('escs',flying?'4 / 4 ACTIVE':'0 / 4 ACTIVE');setText('motors',flying?'RUNNING':'STOPPED');setText('props',flying?'ROTATING':'STOPPED');setText('gpsPath','ACTIVE');setText('linkPath',s==='IDLE'?'STANDBY':'PACKETS FLOWING');setText('fcPath',s==='IDLE'?'STANDBY':'COMMANDS FLOWING');setText('escPath',flying?'PWM / DShot':'STANDBY');setText('servo',s==='DELIVERING'?'OPEN':'CLOSED');
 const steps={s1:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'],s2:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'],s3:['ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'],s4:['ENROUTE','HOVERING','DELIVERING','RTL','COMPLETED'],s5:['HOVERING','DELIVERING','RTL','COMPLETED'],s6:['DELIVERING','RTL','COMPLETED'],s7:['RTL','COMPLETED'],s8:['RTL','COMPLETED'],s9:['COMPLETED']};Object.entries(steps).forEach(([id,arr])=>{$(id).className='step '+(arr.includes(s)?'done':'')});const active={TAKEOFF:'s3',ENROUTE:'s4',HOVERING:'s6',DELIVERING:'s7',RTL:'s9'}[s];if(active)$(active).className='step active';if(s==='DELIVERING')$('s8').className='step active';if(s!==lastState){lastState=s;log('STATE → '+s)}}
function explodedPositions(){const k=explodeMode?2.1:1;frame.position.y=explodeMode?0.4:0;fc.position.y=.5*k;gps.position.y=.86*k;companion.position.x=.9*k;battery.position.y=-.44*k;cameraModule.position.z=.9*k;payloadBay.position.z=.94*k;payloadDoor.position.z=.94*k;kit.position.z=.94*k;motors.forEach((m,i)=>{const [x,,z]=corners[i];m.position.set(x*k,.05*k,z*k)});escs.forEach((e,i)=>{const [x,,z]=corners[i];e.position.set(x*.72*k,-.02*k,z*.72*k)});rebuildLines()}
function signalAnimation(dt){if(!last)return;const s=last.state||'IDLE';const p=positions();const speed=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(s)?1.6:.35;if(Math.random()<dt*speed*.65){pulse(path(p.comp,p.fc),0x63b5ff);if(s!=='IDLE')pulse(path(p.fc,p.esc[Math.floor(Math.random()*4)]),0x32e0b0);if(s==='DELIVERING')pulse(path(p.fc,p.door),0xff7c7c)}pulses.forEach((q,i)=>{q.t+=dt*(.65+speed*.25);const f=q.t%1;q.g.position.lerpVectors(q.path[0],q.path[1],f)});for(let i=pulses.length-1;i>=0;i--){if(pulses[i].t>2){scene.remove(pulses[i].g);pulses.splice(i,1)}}}
function physical(dt){const s=last?.state||'IDLE';const fly=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL'].includes(s);const spin=fly?1:0;props.forEach((p,i)=>{p.rotation.y+=(i%2?-.9:.9)*dt*18*spin});if(s==='ENROUTE')aircraft.rotation.z=THREE.MathUtils.lerp(aircraft.rotation.z,-.08,.06);else if(s==='RTL')aircraft.rotation.z=THREE.MathUtils.lerp(aircraft.rotation.z,.08,.06);else aircraft.rotation.z=THREE.MathUtils.lerp(aircraft.rotation.z,0,.06);const targetY=s==='TAKEOFF'?3.5:(fly?3.0:2.2);aircraft.position.y=THREE.MathUtils.lerp(aircraft.position.y,targetY,.035);shadow();kit.visible=s==='DELIVERING'||s==='RTL'||s==='COMPLETED';if(s==='DELIVERING'){payloadDoor.rotation.x=THREE.MathUtils.lerp(payloadDoor.rotation.x,-.6,.1);kit.position.y=-1.05}else{payloadDoor.rotation.x=THREE.MathUtils.lerp(payloadDoor.rotation.x,0,.08);kit.position.y=-.72}}
function shadow(){if(!scene.getObjectByName('airShadow')){const g=new THREE.Mesh(new THREE.CircleGeometry(2.0,40),new THREE.MeshBasicMaterial({color:0x000000,transparent:true,opacity:.25}));g.rotation.x=-Math.PI/2;g.name='airShadow';scene.add(g)}scene.getObjectByName('airShadow').position.set(aircraft.position.x,.12,aircraft.position.z)}
async function poll(){if(!live)return;try{const r=await fetch('/drone_state',{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);$('source').textContent='LIVE HUB';apply(await r.json())}catch(e){$('source').textContent='HUB ERROR';log('Hub read failed: '+e.message)}pollTimer=setTimeout(poll,400)}
$('live').onclick=()=>{live=true;log('Live hub mode enabled');poll()};$('explode').onclick=()=>{explodeMode=true;explodedPositions();log('Exploded hardware view')};$('assemble').onclick=()=>{explodeMode=false;explodedPositions();log('Assembled hardware view')};$('trigger').onclick=async()=>{try{const la=21.1280,lo=79.0470;log('TEST DISTRESS → /node-alert');const r=await fetch(`/node-alert?node=DRONE-HARDWARE&lat=${la}&lon=${lo}&event=1&conf=.99&pir=1&light=30`,{method:'POST'});const j=await r.json();log(j.dispatched?`DISPATCHED ${j.mission_id}`:JSON.stringify(j));live=true;poll()}catch(e){log('Trigger failed: '+e.message)}};
log('3D hardware simulator ready');poll();
const clock=new THREE.Clock();function frame(){requestAnimationFrame(frame);const dt=Math.min(clock.getDelta(),.05);controls.update();signalAnimation(dt);physical(dt);renderer.render(scene,camera)}frame();
</script>
</body></html>'''
