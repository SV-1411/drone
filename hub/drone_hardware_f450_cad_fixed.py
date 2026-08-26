"""Stable F450 hardware CAD view using the real mathieuvenot/F450 Rhino frame."""
from fastapi.responses import HTMLResponse


def attach(app):
    @app.get("/drone-hardware", response_class=HTMLResponse)
    def drone_hardware_page():
        return HTML


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanniKawachh · DJI F450 Hardware CAD</title>
<style>
:root{--bg:#05090d;--line:#294653;--txt:#edf7fa;--muted:#90a7b4;--power:#ffb34c;--data:#69baff;--ctrl:#39e6b8;--pay:#ff6878}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--txt);font:12px Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 440px;height:100vh}#view{position:relative;min-width:0}#c{width:100%;height:100%;display:block}.top{position:absolute;z-index:20;left:13px;right:13px;top:13px;display:flex;justify-content:space-between;pointer-events:none}.pill{background:#07131eed;border:1px solid var(--line);border-radius:999px;padding:9px 12px}.pill b{color:#fff}
#side{overflow:auto;background:#07121bf8;border-left:1px solid var(--line);padding:13px}.title{font-size:22px;font-weight:900}.sub,.note{font-size:10px;color:var(--muted);line-height:1.55}.card{background:#0b1821;border:1px solid var(--line);border-radius:12px;padding:11px;margin:9px 0}.lab{font-size:10px;letter-spacing:.1em;color:var(--muted);font-weight:900}.big{font-size:27px;font-weight:900}.ok{color:var(--ctrl)}.warn{color:var(--power)}.row{display:flex;justify-content:space-between;gap:10px;margin:7px 0}.val{font-weight:900;text-align:right}.seq{display:grid;gap:4px}.step{padding:7px 9px;border:1px solid #1d3440;border-radius:8px;color:#667f8c}.step.done{background:#0c211b;color:#b0f4e2;border-color:#2a705e}.step.active{background:#231a0f;color:#ffe0a1;border-color:#936827}.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:3px;align-items:center}.node{padding:7px 3px;border:1px solid #294653;border-radius:7px;text-align:center;font-size:8px}.node.active{border-color:var(--ctrl);box-shadow:0 0 14px #39e6b833}.btns{display:grid;grid-template-columns:1fr 1fr;gap:7px}.btn{border:1px solid var(--line);border-radius:8px;padding:10px;background:#122532;color:#fff;font-weight:900;cursor:pointer}.btn.primary{background:#0c3026;border-color:#2c705e}.btn.warn{background:#2a2113;border-color:#75552b}.btn:disabled{opacity:.45}.status{padding:9px;border:1px solid var(--line);border-radius:8px;background:#061016;font-size:10px;margin:8px 0}.good{border-color:#2a705e;color:#b4f5e4}.bad{border-color:#913443;color:#ffc0c7}.log{height:88px;overflow:auto;background:#051017;border:1px solid #17303d;border-radius:7px;padding:6px;font:9px/1.45 monospace;color:#8fb9c7}.tag{padding:5px 7px;border:1px solid currentColor;border-radius:6px;background:#061017ee;font-size:10px;white-space:nowrap}.tag small{display:block;color:#a5bac4;font-size:8px;margin-top:2px}
@media(max-width:900px){#app{grid-template-columns:1fr}#side{position:absolute;z-index:50;right:0;top:0;bottom:0;width:min(440px,96vw);box-shadow:-20px 0 50px #000c}}
</style></head><body>
<div id="app">
<section id="view"><div class="top"><div class="pill"><b>VANNIKAWACHH</b> · DJI F450 / PIXHAWK HARDWARE CAD</div><div class="pill">SOURCE: <b id="source">LOADING CAD</b></div></div><canvas id="c"></canvas></section>
<aside id="side">
<div class="title">Actual F450 Frame + Flight Hardware</div>
<div class="sub">Real Rhino F450 frame from mathieuvenot/F450 with overlaid flight hardware. Hardware state follows the same /drone_state mission feed.</div>
<div class="card"><div class="lab">LIVE MISSION</div><div id="state" class="big ok">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="val">—</span></div><div class="row"><span>Speed</span><span id="speed" class="val">0.0 m/s</span></div><div class="row"><span>Altitude</span><span id="alt" class="val">0.0 m</span></div><div class="row"><span>Motor RPM</span><span id="rpm" class="val">0</span></div></div>
<div class="card"><div class="lab">REFERENCE BUILD</div><div class="row"><span>Frame</span><span class="val">DJI Flame Wheel F450</span></div><div class="row"><span>Motors</span><span class="val">DJI 2312E 960KV ×4</span></div><div class="row"><span>Props</span><span class="val">DJI 9450 ×4</span></div><div class="row"><span>Flight controller</span><span class="val">Pixhawk 2.1 / CubeOrange</span></div><div class="row"><span>GPS</span><span class="val">F9P RTK + compass</span></div></div>
<div class="card"><div class="lab">POWER / CONTROL / PAYLOAD</div><div class="row"><span>LiPo → PDB → ESC ×4</span><span id="powerState" class="val" style="color:var(--power)">READY</span></div><div class="row"><span>ESC → motors → props</span><span id="motorState" class="val">OFF</span></div><div class="row"><span>GPS + IMU → Pixhawk</span><span class="val" style="color:var(--data)">DATA</span></div><div class="row"><span>ESP32 → Hub → companion</span><span id="link" class="val" style="color:var(--data)">STANDBY</span></div><div class="row"><span>Pixhawk → ESC control</span><span id="ctrl" class="val" style="color:var(--ctrl)">STANDBY</span></div><div class="row"><span>Servo → health kit</span><span id="servo" class="val" style="color:var(--pay)">CLOSED</span></div></div>
<div class="card"><div class="lab">MISSION SEQUENCE</div><div class="seq"><div id="s1" class="step">Distress trigger</div><div id="s2" class="step">Hub / companion command</div><div id="s3" class="step">Pixhawk arm</div><div id="s4" class="step">ESC + rotor spool</div><div id="s5" class="step">Vertical takeoff</div><div id="s6" class="step">Fly / hover at target</div><div id="s7" class="step">Open payload bay</div><div id="s8" class="step">Release health kit</div><div id="s9" class="step">RTL / land</div></div></div>
<div class="card"><div class="lab">SIGNAL CHAIN</div><div class="chain"><div id="n1" class="node">ESP32<br>SENSOR</div><div>→</div><div id="n2" class="node">HUB<br>DISPATCH</div><div>→</div><div id="n3" class="node">PIXHAWK<br>ARDUPILOT</div><div>→</div><div id="n4" class="node">ESC ×4<br>+ SERVO</div></div></div>
<div class="btns"><button id="live" class="btn primary">LIVE HUB</button><button id="test" class="btn">TEST DISTRESS</button><button id="explode" class="btn warn">EXPLODE CAD + HARDWARE</button><button id="assemble" class="btn">ASSEMBLE</button></div>
<div id="status" class="status">Loading real F450 CAD…</div><div id="log" class="log"></div>
<div class="note">CAD source: mathieuvenot/F450, 3D-Print/3D-Model/F450_Frame.3dm</div>
</aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {CSS2DRenderer,CSS2DObject} from 'three/addons/renderers/CSS2DRenderer.js';
import {Rhino3dmLoader} from 'three/addons/loaders/3DMLoader.js';
const $=id=>document.getElementById(id); const FRAME='https://raw.githubusercontent.com/mathieuvenot/F450/master/3D-Print/3D-Model/F450_Frame.3dm';
const log=m=>{const e=$('log');e.innerHTML+='<div>'+new Date().toLocaleTimeString()+' · '+m+'</div>';e.scrollTop=e.scrollHeight};
const setStatus=(m,bad=false)=>{$('status').textContent=m;$('status').className='status '+(bad?'bad':'good')};
const scene=new THREE.Scene();scene.background=new THREE.Color(0x05090d);scene.fog=new THREE.Fog(0x05090d,18,70);
const cam=new THREE.PerspectiveCamera(42,1,.05,200);cam.position.set(7.5,5.5,9.5);
const renderer=new THREE.WebGLRenderer({canvas:$('c'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
const labels=new CSS2DRenderer();labels.domElement.style.position='absolute';labels.domElement.style.inset='0';labels.domElement.style.pointerEvents='none';$('view').appendChild(labels.domElement);
const controls=new OrbitControls(cam,renderer.domElement);controls.enableDamping=true;controls.minDistance=4;controls.maxDistance=35;controls.target.set(0,0,0);
scene.add(new THREE.HemisphereLight(0xdbefff,0x121820,2));const key=new THREE.DirectionalLight(0xffffff,3);key.position.set(8,12,6);scene.add(key);scene.add(new THREE.GridHelper(40,20,0x173640,0x0c242d));
const root=new THREE.Group();scene.add(root);const hardware=new THREE.Group();root.add(hardware);const signals=new THREE.Group();root.add(signals);
const mk=(c,m=.4,r=.32)=>new THREE.MeshStandardMaterial({color:c,metalness:m,roughness:r});
const M={black:mk(0x20252a,.6,.26),board:mk(0x1e665e,.2,.4),blue:mk(0x245a78,.3,.34),gold:mk(0xb87a1e,.5,.28),red:mk(0x9d3540,.2,.38),white:mk(0xdfe5e8,.15,.3)};
const rotors=[],escs=[],dynamic=[]; let exploded=false,rpm=0,state='IDLE',lastState='IDLE',cadLoaded=false;
function cube(x,y,z,m){const o=new THREE.Mesh(new THREE.BoxGeometry(x,y,z),m);o.castShadow=o.receiveShadow=true;return o}
function cyl(r,h,m){const o=new THREE.Mesh(new THREE.CylinderGeometry(r,r,h,24),m);o.castShadow=o.receiveShadow=true;return o}
function tag(parent,title,sub,color){const d=document.createElement('div');d.className='tag';d.style.color=color;d.innerHTML='<b>'+title+'</b><small>'+sub+'</small>';parent.add(new CSS2DObject(d));}
function makeRotor(x,z,i){const g=new THREE.Group();g.position.set(x,.32,z);g.userData.dir=i%2===0?1:-1;g.userData.base=g.position.clone();g.userData.ex=new THREE.Vector3(x*1.08,1.6,z*1.08);const hub=cyl(.12,.1,M.black);g.add(hub);for(let j=0;j<2;j++){const p=cube(1.25,.045,.1,M.white);p.position.y=.08;p.rotation.y=j*Math.PI/2;g.add(p)}hardware.add(g);rotors.push(g)}
function addHardware(){
 const pos=[[-2.55,-2.05],[2.55,-2.05],[-2.55,2.05],[2.55,2.05]];
 pos.forEach((p,i)=>{const esc=cube(.42,.16,.62,M.board);esc.position.set(p[0]*.72,.55,p[1]*.72);esc.userData.base=esc.position.clone();esc.userData.ex=new THREE.Vector3(p[0]*.84,1.35,p[1]*.84);hardware.add(esc);escs.push(esc);tag(esc,'ESC '+(i+1),'APD 80A reference','#39e6b8');const motor=cyl(.23,.20,M.black);motor.position.set(p[0],.72,p[1]);motor.userData.base=motor.position.clone();motor.userData.ex=new THREE.Vector3(p[0],1.9,p[1]);hardware.add(motor);tag(motor,'MOTOR '+(i+1),'DJI 2312E 960KV','#39e6b8');makeRotor(p[0],p[1],i)});
 const add=(o,title,sub,color,ex)=>{o.userData.base=o.position.clone();o.userData.ex=ex;hardware.add(o);tag(o,title,sub,color);dynamic.push(o);return o};
 const lipo=add(cube(1.55,.42,.72,M.black),'LiPo','4S 4500 mAh','#ffb34c',new THREE.Vector3(-3.6,-.9,0));lipo.position.set(0,-.7,0);
 const pwr=add(cube(.9,.18,.7,M.gold),'POWER MODULE / PDB','battery distribution','#ffb34c',new THREE.Vector3(-2.1,-.1,0));pwr.position.set(0,-.27,0);pwr.userData.base=pwr.position.clone();
 const fc=add(cube(1.15,.20,.8,M.blue),'PIXHAWK 2.1 / CUBEORANGE','ArduPilot flight controller','#39e6b8',new THREE.Vector3(0,2.2,0));fc.position.set(0,.72,0);fc.userData.base=fc.position.clone();
 const gps=add(cyl(.28,.12,M.white),'F9P GPS + COMPASS','RTK reference','#69baff',new THREE.Vector3(0,2.7,.8));gps.position.set(0,1.22,.25);gps.userData.base=gps.position.clone();
 const telem=add(cube(.65,.16,.42,M.red),'915 MHz TELEMETRY','companion / link','#69baff',new THREE.Vector3(-2.2,1.8,.4));telem.position.set(-.75,.96,.02);telem.userData.base=telem.position.clone();
 const servo=add(cube(.48,.20,.36,M.red),'PAYLOAD SERVO','health-kit release','#ff6878',new THREE.Vector3(2,.4,0));servo.position.set(.76,-.04,0);servo.userData.base=servo.position.clone();
 const bay=add(cube(1,.28,.9,M.gold),'PAYLOAD BAY','health kit','#ff6878',new THREE.Vector3(2,-.2,.9));bay.position.set(0,-.18,.72);bay.userData.base=bay.position.clone();
 return {lipo,pwr,fc,gps,telem,servo,bay};
}
const H=addHardware();
function link(a,b,c){const g=new THREE.BufferGeometry().setFromPoints([a,b]);signals.add(new THREE.Line(g,new THREE.LineBasicMaterial({color:c,transparent:true,opacity:.6})))}
link(H.lipo.position,H.pwr.position,0xffb34c);link(H.pwr.position,H.fc.position,0xffb34c);link(H.fc.position,H.gps.position,0x69baff);link(H.telem.position,H.fc.position,0x69baff);escs.forEach(e=>link(H.fc.position,e.position,0x39e6b8));link(H.fc.position,H.servo.position,0xff6878);escs.forEach(e=>link(H.pwr.position,e.position,0xffb34c));
function validVec(v){return v&&Number.isFinite(v.x)&&Number.isFinite(v.y)&&Number.isFinite(v.z)}
function setExploded(on){exploded=!!on;[...dynamic,...escs,...rotors].forEach(o=>{const u=o&&o.userData; if(!u||!validVec(u.base)||!validVec(u.ex)) return; o.position.copy(exploded?u.ex:u.base)});$('explode').textContent=exploded?'ASSEMBLE':'EXPLODE CAD + HARDWARE';setStatus(exploded?'Exploded engineering view':'Assembled F450 view');}
function apply(d){state=d.state||'IDLE';rpm=Number(d.motor_rpm||0);$('state').textContent=state;$('state').className='big '+(['TAKEOFF','ENROUTE','RTL','LANDING'].includes(state)?'warn':'ok');$('source').textContent=cadLoaded?'REAL F450 CAD':'LOADING CAD';$('mission').textContent=d.mission_id||'—';$('speed').textContent=Number(d.speed_ms||0).toFixed(1)+' m/s';$('alt').textContent=Number(d.altitude_m||0).toFixed(1)+' m';$('rpm').textContent=Math.round(rpm);const active=['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(state);$('powerState').textContent=active?'ACTIVE':'READY';$('motorState').textContent=active?'RUNNING':'OFF';$('link').textContent=state==='IDLE'?'STANDBY':'ACTIVE';$('ctrl').textContent=active?'PWM / DShot':'STANDBY';$('servo').textContent=state==='DELIVERING'?'OPEN':'CLOSED';['n1','n2','n3','n4'].forEach(x=>$(x).classList.remove('active'));if(state!=='IDLE')$('n1').classList.add('active'),$('n2').classList.add('active');if(active)$('n3').classList.add('active');if(['DELIVERING','RTL','LANDING','COMPLETED'].includes(state))$('n4').classList.add('active');if(state!==lastState){log('STATE → '+state);lastState=state}}
function poll(){fetch('/drone_state?ts='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(apply).catch(e=>setStatus('Hub error: '+e.message,true)).finally(()=>setTimeout(poll,800))}
$('live').onclick=()=>poll();$('test').onclick=async()=>{const b=$('test');b.disabled=true;setStatus('Sending distress…');try{const r=await fetch('/node-alert?node=WEB-F450-CAD&lat=21.128&lon=79.047&event=1&conf=0.99&pir=1&light=30');if(!r.ok)throw Error('HTTP '+r.status);log('DISTRESS → accepted');setStatus('Distress accepted')}catch(e){log('TRIGGER ERROR → '+e.message);setStatus('Trigger failed: '+e.message,true)}finally{setTimeout(()=>b.disabled=false,600)}};$('explode').onclick=()=>setExploded(!exploded);$('assemble').onclick=()=>setExploded(false);
function resize(){const r=$('view').getBoundingClientRect();cam.aspect=r.width/r.height;cam.updateProjectionMatrix();renderer.setSize(r.width,r.height,false);labels.setSize(r.width,r.height)}
addEventListener('resize',resize);resize();setExploded(false);
const loader=new Rhino3dmLoader();loader.setLibraryPath('https://cdn.jsdelivr.net/npm/rhino3dm@8.17.0/');loader.setWorkerLimit(2);loader.load(FRAME,obj=>{obj.rotation.x=-Math.PI/2;const box=new THREE.Box3().setFromObject(obj);const c=box.getCenter(new THREE.Vector3());const s=box.getSize(new THREE.Vector3());obj.position.sub(c);obj.scale.setScalar(6/Math.max(s.x,s.y,s.z));root.add(obj);cadLoaded=true;$('source').textContent='REAL F450 CAD';setStatus('REAL F450 CAD loaded');log('Loaded F450_Frame.3dm');},undefined,e=>{console.error(e);setStatus('Real F450 CAD failed to load',true);log('CAD load error: '+e.message)});
poll();
const clock=new THREE.Clock();function animate(){requestAnimationFrame(animate);const dt=clock.getDelta();const spin=rpm*Math.PI*2/60*dt*.75;rotors.forEach(r=>r.rotation.y+=spin*r.userData.dir);controls.update();renderer.render(scene,cam);labels.render(scene,cam)}animate();
</script></body></html>'''
