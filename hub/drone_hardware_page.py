"""Interactive 3D onboard-hardware simulator for VanniKawachh.

The aircraft shell is a directly loaded GLB so its scene can be controlled in
browser JavaScript. Sketchfab iframe embedding is deliberately not used because
cross-origin iframes cannot expose rotor nodes to the parent page.

The view has two modes:
- assembled: aircraft + live animated rotors + telemetry
- exploded: aircraft shell separated from Pixhawk, GPS, battery/PDB, ESCs,
  motors and payload hardware, with animated power/data/control paths

Mission state comes from the deployed /drone_state endpoint.
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
<title>VanniKawachh | Drone Hardware Integration</title>
<style>
:root{--bg:#04090e;--panel:#07131c;--line:#274451;--txt:#edf7fa;--muted:#8ca5b4;--power:#ffb34c;--data:#68b8ff;--ctrl:#35e2b3;--payload:#ff6b79;--ok:#35e2b3;--bad:#ff6875}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--txt);font:12px Inter,Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 440px;width:100vw;height:100vh}#sceneWrap{position:relative;min-width:0;min-height:0}#c{width:100%;height:100%;display:block}.top{position:absolute;z-index:5;left:12px;right:12px;top:12px;display:flex;justify-content:space-between;pointer-events:none}.pill{background:#06131ee8;border:1px solid var(--line);border-radius:999px;padding:8px 12px;backdrop-filter:blur(8px)}.pill b{color:#fff}
#side{overflow:auto;background:#07121bf8;border-left:1px solid var(--line);padding:13px}.title{font-size:21px;font-weight:900}.sub,.note{font-size:10px;line-height:1.5;color:var(--muted)}.card{background:linear-gradient(180deg,#0d1d27,#08131c);border:1px solid var(--line);border-radius:12px;padding:11px;margin:9px 0}.lab{font-size:10px;letter-spacing:.1em;color:var(--muted);font-weight:900}.big{font-size:28px;font-weight:900;margin:2px 0}.ok{color:var(--ok)}.warn{color:var(--power)}.bad{color:var(--bad)}.row{display:flex;justify-content:space-between;gap:8px;margin:7px 0}.val{font-weight:800;text-align:right}.power{color:var(--power)}.data{color:var(--data)}.ctrl{color:var(--ctrl)}.payload{color:var(--payload)}
.buttons{display:grid;grid-template-columns:1fr 1fr;gap:7px}.btn{border:1px solid var(--line);border-radius:8px;padding:10px;background:#112432;color:white;font-weight:900;cursor:pointer}.btn.primary{background:#0d2d25;border-color:#2b725f}.btn.warn{background:#2a2113;border-color:#77562a}.btn:disabled{opacity:.45;cursor:wait}.btn:hover:not(:disabled){filter:brightness(1.12)}
.seq{display:grid;gap:4px}.step{padding:7px 9px;border:1px solid #1d3440;border-radius:8px;background:#09151d;color:#667f8c}.step.active{border-color:#8e672b;background:#221a10;color:#ffe0a1;font-weight:800}.step.done{border-color:#2a6e5c;background:#0c211b;color:#aef4e1}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#394c55;margin-right:7px}.step.active .dot{background:var(--power)}.step.done .dot{background:var(--ok)}
.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:3px;align-items:center}.node{padding:7px 3px;text-align:center;font-size:8px;border:1px solid #294554;border-radius:7px;background:#0a1922}.node.active{border-color:var(--ok);box-shadow:0 0 14px #35e2b322}.arr{color:var(--ok)}
#status{padding:8px 10px;border:1px solid #1c3744;border-radius:8px;background:#061016;font-size:10px;min-height:18px;margin-bottom:8px}.status-ok{border-color:#2a6e5c!important;color:#aef4e1}.status-err{border-color:#913443!important;color:#ffb8c1}.status-busy{border-color:#8e672b!important;color:#ffe0a1}#log{height:92px;overflow:auto;background:#051017;border:1px solid #17303d;border-radius:7px;padding:6px;font:9px/1.5 ui-monospace,Consolas,monospace;color:#8fb9c7}
@media(max-width:900px){#app{grid-template-columns:1fr}#side{position:absolute;z-index:20;right:0;top:0;bottom:0;width:min(440px,95vw);box-shadow:-20px 0 50px #000c}}
</style>
</head>
<body>
<div id="app">
<section id="sceneWrap"><div class="top"><div class="pill"><b>VANNIKAWACHH</b> · PHYSICAL DRONE / HARDWARE INTEGRATION</div><div class="pill">SOURCE: <b id="source">CHECKING…</b></div></div><canvas id="c"></canvas></section>
<aside id="side">
<div class="title">Real On-Board Architecture</div>
<div class="sub">This is the Wokwi-style physical view: a directly loaded 3D aircraft shell, four controllable propellers, and an engineering exploded assembly showing the proposed Pixhawk/ArduPilot, battery, PDB, ESCs, motors, GPS/compass, companion link and payload hardware.</div>
<div class="card"><div class="lab">LIVE MISSION</div><div id="state" class="big ok">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="val">—</span></div><div class="row"><span>Speed</span><span id="speed" class="val">0.0 m/s</span></div><div class="row"><span>Altitude</span><span id="alt" class="val">0.0 m</span></div><div class="row"><span>Motor RPM</span><span id="rpm" class="val">0</span></div><div class="row"><span>Hub</span><span id="hub" class="val">CHECKING</span></div></div>
<div class="card"><div class="lab">POWER PATH</div><div class="row"><span>LiPo battery</span><span class="val power">ON</span></div><div class="row"><span>PDB / power module</span><span id="pdb" class="val power">READY</span></div><div class="row"><span>ESC ×4</span><span id="esc" class="val">0 / 4</span></div><div class="row"><span>BLDC motors ×4</span><span id="motors" class="val">STOPPED</span></div><div class="row"><span>Props</span><span id="props" class="val">STOPPED</span></div></div>
<div class="card"><div class="lab">CONTROL + DATA</div><div class="row"><span>GPS + compass + IMU → Pixhawk</span><span class="val data">DATA</span></div><div class="row"><span>ESP32 → hub → companion</span><span id="link" class="val data">STANDBY</span></div><div class="row"><span>Companion → Pixhawk</span><span id="fc" class="val ctrl">STANDBY</span></div><div class="row"><span>Pixhawk → ESC control</span><span id="escsig" class="val ctrl">STANDBY</span></div><div class="row"><span>Servo → payload</span><span id="servo" class="val payload">CLOSED</span></div></div>
<div class="card"><div class="lab">SEQUENCE</div><div class="seq"><div id="s1" class="step"><span class="dot"></span>Distress received</div><div id="s2" class="step"><span class="dot"></span>Mission/link command</div><div id="s3" class="step"><span class="dot"></span>Pixhawk arms</div><div id="s4" class="step"><span class="dot"></span>ESCs spool</div><div id="s5" class="step"><span class="dot"></span>Vertical lift</div><div id="s6" class="step"><span class="dot"></span>Cruise / hover</div><div id="s7" class="step"><span class="dot"></span>Payload servo opens</div><div id="s8" class="step"><span class="dot"></span>Health kit released</div><div id="s9" class="step"><span class="dot"></span>RTL / landing</div></div></div>
<div class="card"><div class="lab">SIGNAL CHAIN</div><div class="chain"><div id="n1" class="node">ESP32<br>SENSOR</div><div class="arr">→</div><div id="n2" class="node">HUB<br>DISPATCH</div><div class="arr">→</div><div id="n3" class="node">PIXHAWK<br>ARDUPILOT</div><div class="arr">→</div><div id="n4" class="node">ESCs +<br>SERVO</div></div></div>
<div class="buttons"><button class="btn primary" id="live">LIVE HUB</button><button class="btn" id="trigger">TEST DISTRESS</button><button class="btn" id="assembled">ASSEMBLED</button><button class="btn warn" id="exploded">EXPLODED</button></div>
<div id="status">Initializing 3D aircraft and hub connection…</div><div class="card"><div class="lab">EVENT LOG</div><div id="log"></div></div>
<div class="note">The outer aircraft is a directly loaded GLB so the browser can control the scene. The props are independent simulated motor elements tied to mission RPM. The actual flight-control physics remains ArduPilot SITL/Gazebo; this page explains and visualizes the proposed hardware integration.</div>
</aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

const $=id=>document.getElementById(id);
const LOG=m=>{const e=$("log");e.innerHTML+=`<div>${new Date().toLocaleTimeString()} · ${m}</div>`;e.scrollTop=e.scrollHeight};
const status=(m,k='')=>{$("status").textContent=m;$('status').className='status-'+(k||'')};

const scene=new THREE.Scene();scene.background=new THREE.Color(0x04090e);scene.fog=new THREE.Fog(0x04090e,14,65);
const camera=new THREE.PerspectiveCamera(42,1,.1,200);camera.position.set(9,6,12);
const renderer=new THREE.WebGLRenderer({canvas:$('c'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.target.set(0,1.5,0);controls.minDistance=4;controls.maxDistance=35;
scene.add(new THREE.HemisphereLight(0xb8ddff,0x111820,2));const sun=new THREE.DirectionalLight(0xffffff,3);sun.position.set(8,12,6);sun.castShadow=true;scene.add(sun);scene.add(new THREE.GridHelper(40,20,0x193744,0x0d242e));

const aircraft=new THREE.Group();aircraft.position.y=2.2;scene.add(aircraft);
const components=new THREE.Group();scene.add(components);
const shellGroup=new THREE.Group();aircraft.add(shellGroup);
const internalGroup=new THREE.Group();aircraft.add(internalGroup);
const pulseGroup=new THREE.Group();scene.add(pulseGroup);

const matMetal=new THREE.MeshStandardMaterial({color:0x242d31,metalness:.65,roughness:.28});
const matBoard=new THREE.MeshStandardMaterial({color:0x17414b,metalness:.15,roughness:.6});
const matBattery=new THREE.MeshStandardMaterial({color:0x34363b,metalness:.25,roughness:.45});
const matGold=new THREE.MeshStandardMaterial({color:0xd08a24,metalness:.45,roughness:.3});
const matBlue=new THREE.MeshStandardMaterial({color:0x245a7a,metalness:.25,roughness:.35});
const matRed=new THREE.MeshStandardMaterial({color:0x9d3941,metalness:.2,roughness:.4});
const matWhite=new THREE.MeshStandardMaterial({color:0xdfe7ea,metalness:.15,roughness:.35,transparent:true,opacity:.92});

let model=null, modelCenter=new THREE.Vector3(), modelSize=new THREE.Vector3(5,1.5,4), modelReady=false;
const propGroups=[];const motorMeshes=[];const escMeshes=[];
const propPositions=[[-1,0,-.72],[1,0,-.72],[-1,0,.72],[1,0,.72]];

function makeProp(clockwise){
  const g=new THREE.Group();
  const hub=new THREE.Mesh(new THREE.CylinderGeometry(.16,.16,.12,24),matMetal);hub.rotation.x=Math.PI/2;g.add(hub);
  for(let i=0;i<2;i++){
    const b=new THREE.Mesh(new THREE.BoxGeometry(1.35,.035,.12),matWhite);b.position.y=.08;b.rotation.y=i*Math.PI/2;g.add(b);
  }
  g.userData.dir=clockwise?1:-1;return g;
}

const loader=new GLTFLoader();
loader.load('https://cdn.jsdelivr.net/gh/amvlab/aircraft-models@main/models/drone_nologo.glb',g=>{
  model=g.scene;
  model.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;if(/prop|rotor|blade/i.test(o.name||''))o.visible=false;}});
  const box=new THREE.Box3().setFromObject(model);modelCenter.copy(box.getCenter(new THREE.Vector3()));modelSize.copy(box.getSize(new THREE.Vector3()));
  model.position.sub(modelCenter);
  const scale=5.0/Math.max(modelSize.x,modelSize.z);model.scale.setScalar(scale);modelSize.multiplyScalar(scale);
  shellGroup.add(model);
  const halfX=modelSize.x*.38, halfZ=modelSize.z*.34;
  propPositions.splice(0,4,[-halfX,.08,-halfZ],[halfX,.08,-halfZ],[-halfX,.08,halfZ],[halfX,.08,halfZ]);
  propPositions.forEach((p,i)=>{const pg=makeProp(i%2===0);pg.position.set(...p);shellGroup.add(pg);propGroups.push(pg);});
  modelReady=true;fitAircraft();LOG('3D aircraft shell loaded');status('3D aircraft loaded — live hardware simulation ready','ok');
},undefined,e=>{LOG('GLB load failed: '+e.message);status('GLB failed to load; retry the page','err');});

function board(w,h,d,mat=matBoard){const g=new THREE.Group();const base=new THREE.Mesh(new THREE.BoxGeometry(w,.12,d),mat);base.castShadow=true;g.add(base);for(let x=-w/2+.08;x<w/2-.07;x+=.16){const pin=new THREE.Mesh(new THREE.BoxGeometry(.025,.04,.04),new THREE.MeshStandardMaterial({color:0xb6c5ca,metalness:.7}));pin.position.set(x,.09,d/2-.05);g.add(pin);}return g;}
function makeHardware(){
  // Pixhawk
  const fc=board(.95,.18,.65);fc.position.set(0,1.35,0);fc.userData.name='PIXHAWK / ARDUPILOT';internalGroup.add(fc);
  // GPS puck
  const gps=new THREE.Mesh(new THREE.CylinderGeometry(.26,.28,.1,32),matBlue);gps.position.set(0,1.95,0);gps.userData.name='GPS + COMPASS';internalGroup.add(gps);
  // Battery + strap
  const bat=new THREE.Mesh(new THREE.BoxGeometry(1.65,.38,.72),matBattery);bat.position.set(0,-.62,0);bat.userData.name='LiPo BATTERY';internalGroup.add(bat);
  const strap=new THREE.Mesh(new THREE.BoxGeometry(1.7,.04,.82),matGold);strap.position.set(0,-.41,0);internalGroup.add(strap);
  // PDB
  const pdb=board(.85,.12,.6,matGold);pdb.position.set(0,-.08,0);pdb.userData.name='PDB / POWER MODULE';internalGroup.add(pdb);
  // companion
  const comp=board(.8,.12,.52,matBlue);comp.position.set(.0,.9,.95);comp.userData.name='COMPANION / LoRa';internalGroup.add(comp);
  // payload servo + bay
  const servo=new THREE.Mesh(new THREE.BoxGeometry(.4,.22,.3),matRed);servo.position.set(0,.1,1.02);servo.userData.name='PAYLOAD SERVO';internalGroup.add(servo);
  const bay=new THREE.Mesh(new THREE.BoxGeometry(.9,.45,.7),matGold);bay.position.set(0,-.45,1.02);bay.userData.name='HEALTH KIT BAY';internalGroup.add(bay);
  // ESCs + motors
  const corners=[[-1.65,-.9],[1.65,-.9],[-1.65,.9],[1.65,.9]];
  corners.forEach(([x,z],i)=>{
    const esc=new THREE.Mesh(new THREE.BoxGeometry(.42,.16,.62),new THREE.MeshStandardMaterial({color:0x1d2529,metalness:.5,roughness:.4}));esc.position.set(x*.78,.28,z*.78);esc.userData.name='ESC '+(i+1);internalGroup.add(esc);escMeshes.push(esc);
    const motor=new THREE.Mesh(new THREE.CylinderGeometry(.25,.25,.22,24),matMetal);motor.rotation.x=Math.PI/2;motor.position.set(x,.28,z);motor.userData.name='BLDC MOTOR '+(i+1);internalGroup.add(motor);motorMeshes.push(motor);
  });
}
makeHardware();

const lineMat={power:new THREE.LineBasicMaterial({color:0xffb34c,transparent:true,opacity:.5}),data:new THREE.LineBasicMaterial({color:0x68b8ff,transparent:true,opacity:.55}),ctrl:new THREE.LineBasicMaterial({color:0x35e2b3,transparent:true,opacity:.6}),payload:new THREE.LineBasicMaterial({color:0xff6b79,transparent:true,opacity:.6})};
function makeLine(a,b,mat){const geom=new THREE.BufferGeometry().setFromPoints([a,b]);const l=new THREE.Line(geom,mat);internalGroup.add(l);return l;}
makeLine(new THREE.Vector3(0,-.62,0),new THREE.Vector3(0,-.08,0),lineMat.power);
escMeshes.forEach(e=>makeLine(new THREE.Vector3(0,-.08,0),e.position,lineMat.power));
makeLine(new THREE.Vector3(0,1.95,0),new THREE.Vector3(0,1.35,0),lineMat.data);
makeLine(new THREE.Vector3(0,.9,.95),new THREE.Vector3(0,1.35,0),lineMat.data);
motorMeshes.forEach(m=>makeLine(new THREE.Vector3(0,1.35,0),m.position,lineMat.ctrl));
makeLine(new THREE.Vector3(0,1.35,0),new THREE.Vector3(0,.1,1.02),lineMat.payload);

const pulses=[];function pulse(a,b,color){const p=new THREE.Mesh(new THREE.SphereGeometry(.06,12,12),new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:3}));pulseGroup.add(p);p.userData={a:a.clone(),b:b.clone(),t:Math.random(),speed:.45+Math.random()*.25};pulses.push(p);}

let state='IDLE',lastMission=null,live=true,pollTimer=null,lastData=null,exploded=false;
const activeStates=new Set(['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING']);
function setExploded(v){exploded=v;internalGroup.visible=v; if(model)model.visible=true; aircraft.position.y= v?2.4:2.2; shellGroup.scale.setScalar(v?0.82:1); if(v){status('EXPLODED VIEW — internal hardware and signal paths visible','ok')}else{status('ASSEMBLED VIEW — aircraft + animated propulsion','ok')} }
function fitAircraft(){const box=new THREE.Box3().setFromObject(aircraft);const s=box.getSize(new THREE.Vector3());const max=Math.max(s.x,s.y,s.z);const dist=max/2/Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*1.35;camera.position.set(dist*.8,dist*.55,dist*.9);controls.target.copy(box.getCenter(new THREE.Vector3()));controls.update();}
function missionUI(d){const s=d?.state||'IDLE';state=s;lastData=d;$('state').textContent=s;$('state').className='big '+(s==='FAILED'?'bad':(['TAKEOFF','ENROUTE','RTL','LANDING'].includes(s)?'warn':'ok'));$('mission').textContent=d?.mission_id||'—';$('speed').textContent=`${Number(d?.speed_ms||0).toFixed(1)} m/s`;$('alt').textContent=`${Number(d?.altitude_m||0).toFixed(1)} m`;$('rpm').textContent=Math.round(Number(d?.motor_rpm||0)).toLocaleString();$('hub').textContent='ONLINE';$('esc').textContent=activeStates.has(s)?'4 / 4':'0 / 4';$('motors').textContent=activeStates.has(s)?'RUNNING':'STOPPED';$('props').textContent=activeStates.has(s)?'ROTATING':'STOPPED';$('pdb').textContent=activeStates.has(s)?'FEEDING ESCs':'READY';$('link').textContent=s==='IDLE'?'STANDBY':'ACTIVE';$('fc').textContent=activeStates.has(s)?'COMMANDING':'STANDBY';$('escsig').textContent=activeStates.has(s)?'PWM / DShot':'STANDBY';$('servo').textContent=s==='DELIVERING'?'OPEN':'CLOSED';['n1','n2','n3','n4'].forEach(id=>$(id).classList.remove('active'));if(s!=='IDLE')$('n1').classList.add('active');if(s!=='IDLE')$('n2').classList.add('active');if(activeStates.has(s))$('n3').classList.add('active');if(['DELIVERING','RTL','LANDING','COMPLETED'].includes(s))$('n4').classList.add('active');const done={s1:['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'],s2:['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'],s3:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'],s4:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'],s5:['ENROUTE','HOVERING','DELIVERING','RTL','LANDING'],s6:['HOVERING','DELIVERING','RTL','LANDING','COMPLETED'],s7:['RTL','LANDING','COMPLETED'],s8:['RTL','LANDING','COMPLETED'],s9:['RTL','LANDING','COMPLETED']};Object.entries(done).forEach(([id,a])=>$(id).className='step'+(a.includes(s)?' done':''));const active={ARMING:'s2',TAKEOFF:'s3',ENROUTE:'s6',HOVERING:'s6',DELIVERING:'s7',RTL:'s9',LANDING:'s9'}[s];if(active)$(active).className='step active';if(d?.mission_id&&d.mission_id!==lastMission){LOG('MISSION '+d.mission_id);lastMission=d.mission_id}if(s!==lastState){LOG('STATE → '+s);lastState=s}}
let lastState='IDLE';
async function readHub(){try{const r=await fetch('/drone_state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const d=await r.json();$('source').textContent='LIVE HUB';status('Connected to /drone_state','ok');missionUI(d);return d}catch(e){$('source').textContent='HUB ERROR';$('hub').textContent='OFFLINE';status('Hub error: '+e.message,'err');return null}}
async function trigger(){const b=$('trigger');b.disabled=true;status('Sending distress to /node-alert…','busy');LOG('TEST DISTRESS → /node-alert');try{const r=await fetch('/node-alert?node=WEB-HARDWARE&lat=21.1575&lon=79.1000&event=1&conf=0.99&pir=1&light=30',{cache:'no-store'});const t=await r.text();if(!r.ok)throw new Error('HTTP '+r.status+': '+t);LOG('HUB RESPONSE → '+t);live=true;poll();status('Distress accepted — waiting for ARMED/TAKEOFF','ok')}catch(e){status('Trigger failed: '+e.message,'err');LOG('TRIGGER ERROR → '+e.message)}finally{setTimeout(()=>b.disabled=false,700)}}
function poll(){if(!live)return;readHub().finally(()=>pollTimer=setTimeout(poll,500))}
$('live').onclick=()=>{live=true;status('Connecting to deployed hub…','busy');LOG('LIVE HUB → /drone_state');poll()};$('trigger').onclick=trigger;$('assembled').onclick=()=>setExploded(false);$('exploded').onclick=()=>setExploded(true);
function resize(){const r=$('sceneWrap').getBoundingClientRect();camera.aspect=r.width/r.height;camera.updateProjectionMatrix();renderer.setSize(r.width,r.height,false)}addEventListener('resize',resize);resize();fitAircraft();

function animate(t){requestAnimationFrame(animate);controls.update();const rpm=Number(lastData?.motor_rpm||0);const rad=rpm*Math.PI*2/60*.016;if(activeStates.has(state)){propGroups.forEach((p,i)=>p.rotation.y+=rad*(i%2===0?1:-1));}else{propGroups.forEach(p=>p.rotation.y+=rad*.15)}if(exploded&&lastData){internalGroup.children.forEach(o=>{if(o.userData?.name?.includes('ESC')||o.userData?.name?.includes('MOTOR')){o.position.y+=(o.userData._baseY??(o.userData._baseY=o.position.y+0.0001))-o.position.y}})}pulses.forEach(p=>{p.userData.t=(p.userData.t+p.userData.speed*.016)%1;p.position.lerpVectors(p.userData.a,p.userData.b,p.userData.t)});renderer.render(scene,camera)}requestAnimationFrame(animate);
LOG('Hardware simulator ready');poll();
</script>
</body>
</html>'''
