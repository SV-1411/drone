"""Clean F450 hardware visualization for VanniKawachh.

The airframe uses the public beomsu7/px4-quadrotor-HW-parts F450 meshes.
Electronics that do not have a validated mesh in the source are shown as
engineering callouts/connection anchors rather than giant placeholder blocks.
The view reacts to the same /drone_state mission feed and has a local demo
sequence so the hardware response is visible even before the flight simulator
reports each state.
"""
from fastapi.responses import HTMLResponse


def attach(app):
    @app.get("/drone-hardware", response_class=HTMLResponse)
    def drone_hardware_page():
        return HTML


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanniKawachh · F450 Hardware</title>
<style>
:root{--bg:#050a0f;--line:#294653;--txt:#edf7fa;--muted:#90a7b4;--power:#ffb34c;--data:#69baff;--ctrl:#39e6b8;--pay:#ff6878}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--txt);font:12px Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 430px;height:100vh}#view{position:relative;min-width:0}#c{width:100%;height:100%;display:block}
.top{position:absolute;z-index:10;left:13px;right:13px;top:13px;display:flex;justify-content:space-between;pointer-events:none}.pill{background:#07131eed;border:1px solid var(--line);border-radius:999px;padding:9px 12px}.pill b{color:#fff}
#labels{position:absolute;inset:0;pointer-events:none}.tag{padding:5px 7px;border:1px solid currentColor;border-radius:6px;background:#061017ee;font-size:10px;white-space:nowrap}.tag small{display:block;color:#a5bac4;font-size:8px;margin-top:2px}
#side{overflow:auto;background:#07121bf8;border-left:1px solid var(--line);padding:13px}.title{font-size:22px;font-weight:900}.sub,.note{font-size:10px;color:var(--muted);line-height:1.55}.card{background:#0b1821;border:1px solid var(--line);border-radius:12px;padding:11px;margin:9px 0}.lab{font-size:10px;letter-spacing:.1em;color:var(--muted);font-weight:900}.big{font-size:27px;font-weight:900}.ok{color:var(--ctrl)}.warn{color:var(--power)}.row{display:flex;justify-content:space-between;gap:10px;margin:7px 0}.val{font-weight:900;text-align:right}.seq{display:grid;gap:4px}.step{padding:7px 9px;border:1px solid #1d3440;border-radius:8px;color:#667f8c}.step.done{background:#0c211b;color:#b0f4e2;border-color:#2a705e}.step.active{background:#231a0f;color:#ffe0a1;border-color:#936827}.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:3px;align-items:center}.node{padding:7px 3px;border:1px solid #294653;border-radius:7px;text-align:center;font-size:8px}.node.active{border-color:var(--ctrl);box-shadow:0 0 14px #39e6b833}.btns{display:grid;grid-template-columns:1fr 1fr;gap:7px}.btn{border:1px solid var(--line);border-radius:8px;padding:10px;background:#122532;color:#fff;font-weight:900;cursor:pointer}.btn.primary{background:#0c3026;border-color:#2c705e}.btn.warn{background:#2a2113;border-color:#75552b}.btn:disabled{opacity:.45}.status{padding:9px;border:1px solid var(--line);border-radius:8px;background:#061016;font-size:10px;margin:8px 0}.good{border-color:#2a705e;color:#b4f5e4}.bad{border-color:#913443;color:#ffc0c7}.log{height:88px;overflow:auto;background:#051017;border:1px solid #17303d;border-radius:7px;padding:6px;font:9px/1.45 monospace;color:#8fb9c7}.truth{font-size:9px;color:#8fa8b4;line-height:1.45}
@media(max-width:900px){#app{grid-template-columns:1fr}#side{position:absolute;z-index:50;right:0;top:0;bottom:0;width:min(430px,96vw);box-shadow:-20px 0 50px #000c}}
</style></head>
<body>
<div id="app">
<section id="view"><div class="top"><div class="pill"><b>VANNIKAWACHH</b> · REAL F450 / PIXHAWK HARDWARE</div><div class="pill">SOURCE: <b id="source">F450 GAZEBO MESHES</b></div></div><canvas id="c"></canvas><div id="labels"></div></section>
<aside id="side">
<div class="title">F450 Hardware Reaction</div>
<div class="sub">Real F450 frame, arms, motors, landing gear, battery and prop meshes. Pixhawk, GPS, telemetry, ESC and payload are shown as engineering connection anchors because those parts are not present as validated mesh assets in the F450 mesh package.</div>
<div class="card"><div class="lab">LIVE MISSION</div><div id="state" class="big ok">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="val">—</span></div><div class="row"><span>Speed</span><span id="speed" class="val">0.0 m/s</span></div><div class="row"><span>Altitude</span><span id="alt" class="val">0.0 m</span></div><div class="row"><span>Motor RPM</span><span id="rpm" class="val">0</span></div></div>
<div class="card"><div class="lab">SYSTEM POWER-UP</div><div class="row"><span>Battery</span><span id="battery" class="val" style="color:var(--power)">STANDBY</span></div><div class="row"><span>Pixhawk boot</span><span id="fc" class="val" style="color:var(--ctrl)">OFF</span></div><div class="row"><span>GPS / compass</span><span id="gps" class="val" style="color:var(--data)">NO FIX</span></div><div class="row"><span>Telemetry / companion</span><span id="telem" class="val" style="color:var(--data)">OFFLINE</span></div><div class="row"><span>ESCs ×4</span><span id="esc" class="val">OFF</span></div></div>
<div class="card"><div class="lab">CONTROL / PAYLOAD</div><div class="row"><span>Pixhawk → ESC control</span><span id="ctrl" class="val" style="color:var(--ctrl)">STANDBY</span></div><div class="row"><span>Motors / props</span><span id="motorState" class="val">OFF</span></div><div class="row"><span>Payload servo</span><span id="servo" class="val" style="color:var(--pay)">CLOSED</span></div><div class="row"><span>Health kit</span><span id="kit" class="val" style="color:var(--pay)">SECURED</span></div></div>
<div class="card"><div class="lab">AUTOMATIC MISSION RESPONSE</div><div class="seq"><div id="s1" class="step">1 · Distress received</div><div id="s2" class="step">2 · Power systems ON</div><div id="s3" class="step">3 · Pixhawk boot + GPS lock</div><div id="s4" class="step">4 · Arm + ESC spool</div><div id="s5" class="step">5 · Vertical takeoff</div><div id="s6" class="step">6 · Navigate / hover</div><div id="s7" class="step">7 · Open bay + release kit</div><div id="s8" class="step">8 · RTL + land</div></div></div>
<div class="card"><div class="lab">SIGNAL / POWER FLOW</div><div class="chain"><div id="n1" class="node">ESP32<br>SENSOR</div><div>→</div><div id="n2" class="node">HUB<br>DISPATCH</div><div>→</div><div id="n3" class="node">PIXHAWK<br>ARDUPILOT</div><div>→</div><div id="n4" class="node">ESC ×4<br>+ SERVO</div></div></div>
<div class="btns"><button id="live" class="btn primary">LIVE HUB</button><button id="test" class="btn">TEST DISTRESS</button><button id="labelsBtn" class="btn warn">HIDE LABELS</button><button id="assemble" class="btn">ASSEMBLED VIEW</button></div>
<div id="status" class="status good">READY — distress will trigger automatic power-up / preflight / arm sequence.</div><div id="log" class="log"></div>
<div class="truth"><b>What is physically modeled:</b> F450 airframe/arms/motors/landing gear/battery/prop meshes. <b>What is engineering-simulated:</b> Pixhawk, GPS, telemetry, ESCs and payload actuator. Their state is synchronized to /drone_state; they are intentionally not rendered as fake giant blocks.</div>
</aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {CSS2DRenderer,CSS2DObject} from 'three/addons/renderers/CSS2DRenderer.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
import {ColladaLoader} from 'three/addons/loaders/ColladaLoader.js';
const $=id=>document.getElementById(id);
const RAW='https://raw.githubusercontent.com/beomsu7/px4-quadrotor-HW-parts/main/custom_f450/meshes/';
const U={base:RAW+'base_link.stl',front:RAW+'front_arm_link.stl',back:RAW+'back_arm_link.STL',motor:RAW+'motor_link.STL',leg:RAW+'leg_link.stl',battery:RAW+'battery_link.stl',cw:RAW+'iris_prop_cw.dae',ccw:RAW+'iris_prop_ccw_centered.dae'};
const log=m=>{const e=$('log');e.innerHTML+='<div>'+new Date().toLocaleTimeString()+' · '+m+'</div>';e.scrollTop=e.scrollHeight};
const setStatus=(m,bad=false)=>{$('status').textContent=m;$('status').className='status '+(bad?'bad':'good')};
const scene=new THREE.Scene();scene.background=new THREE.Color(0x050a0f);scene.fog=new THREE.Fog(0x050a0f,2.5,18);
const cam=new THREE.PerspectiveCamera(40,1,.01,100);cam.position.set(1.55,1.1,1.85);
const renderer=new THREE.WebGLRenderer({canvas:$('c'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
const labels=new CSS2DRenderer();labels.domElement.id='labels';labels.domElement.style.position='absolute';labels.domElement.style.inset='0';labels.domElement.style.pointerEvents='none';$('view').appendChild(labels.domElement);
const controls=new OrbitControls(cam,renderer.domElement);controls.enableDamping=true;controls.minDistance=.55;controls.maxDistance=7;controls.target.set(0,.24,0);
scene.add(new THREE.HemisphereLight(0xdbefff,0x11151a,2.2));const key=new THREE.DirectionalLight(0xffffff,3);key.position.set(3,5,4);key.castShadow=true;scene.add(key);scene.add(new THREE.GridHelper(8,16,0x173640,0x0c242d));
const drone=new THREE.Group();scene.add(drone);const anchors=new THREE.Group();drone.add(anchors);const liveParts=[],rotors=[];let rpm=0,state='IDLE',lastState='IDLE',labelsOn=true,demoTimer=null;
const M={frame:new THREE.MeshStandardMaterial({color:0x2a2f33,metalness:.65,roughness:.3}),red:new THREE.MeshStandardMaterial({color:0xa32934,metalness:.4,roughness:.3}),white:new THREE.MeshStandardMaterial({color:0xe5eaed,metalness:.15,roughness:.3}),black:new THREE.MeshStandardMaterial({color:0x1a1e22,metalness:.55,roughness:.3}),marker:new THREE.MeshBasicMaterial({color:0x39e6b8,transparent:true,opacity:.85})};
function tag(parent,t,s,c){const d=document.createElement('div');d.className='tag';d.style.color=c;d.innerHTML='<b>'+t+'</b><small>'+s+'</small>';parent.add(new CSS2DObject(d))}
function reg(o,ex){o.userData.base=o.position.clone();o.userData.ex=ex.clone();liveParts.push(o)}
function stl(url,mat,cb){new STLLoader().load(url,g=>{const o=new THREE.Mesh(g,mat);o.castShadow=o.receiveShadow=true;cb(o)},undefined,e=>{log('STL load failed');console.error(e);setStatus('Mesh load error',true)})}
function dae(url,cb){new ColladaLoader().load(url,d=>{d.scene.traverse(x=>{if(x.isMesh){x.material=M.white;x.castShadow=x.receiveShadow=true}});cb(d.scene)},undefined,e=>{log('Prop mesh load failed');console.error(e)})}
function anchor(pos,title,sub,color){const g=new THREE.Group();g.position.copy(pos);const ring=new THREE.Mesh(new THREE.TorusGeometry(.055,.008,8,24),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.75}));g.add(ring);anchors.add(g);tag(g,title,sub,color);return g}
// Real F450 mesh assets.
stl(U.base,M.frame,o=>{drone.add(o);reg(o,new THREE.Vector3(0,1.0,0));tag(o,'F450 FRAME','base_link.stl','#39e6b8')});
stl(U.leg,M.white,o=>{o.position.set(0,.132,0);drone.add(o);reg(o,new THREE.Vector3(0,-.35,-1.6));tag(o,'LANDING GEAR','leg_link.stl','#cfd9de')});
stl(U.battery,M.black,o=>{o.position.set(-.0254,-.0002,.09);drone.add(o);reg(o,new THREE.Vector3(-.9,-.35,0));tag(o,'BATTERY','battery_link.stl','#ffb34c')});
[[.098,.098,0],[.098,-.098,Math.PI/2],[-.098,-.098,Math.PI],[-.098,.098,-Math.PI/2]].forEach((p,i)=>stl(i%2?U.back:U.front,i<2?M.red:M.white,o=>{o.position.set(p[0],p[1],.171);o.rotation.z=p[2];drone.add(o);reg(o,new THREE.Vector3(p[0]*5,1,p[1]*5));tag(o,'ARM '+(i+1),'F450 arm mesh',i<2?'#ef5560':'#e9eef0')}));
const mp=[[.15988,-.15988],[-.15988,.15988],[.15988,.15988],[-.15988,-.15988]];
mp.forEach((p,i)=>{stl(U.motor,M.black,o=>{o.position.set(p[0],p[1],.173);drone.add(o);tag(o,'MOTOR '+(i+1),'motor_link.STL','#39e6b8')});dae(i%2?U.cw:U.ccw,o=>{o.position.set(p[0],p[1],.206);o.scale.setScalar(.55);o.userData.dir=i%2?-1:1;drone.add(o);rotors.push(o);tag(o,'PROP '+(i+1),'real Collada mesh','#dce7ed')})});
// Engineering connection anchors: no fake boxes.
anchor(new THREE.Vector3(0,.275,0),'PIXHAWK / CUBE','flight controller','#39e6b8');
anchor(new THREE.Vector3(0,.47,-.02),'F9P GPS + COMPASS','RTK / heading','#69baff');
anchor(new THREE.Vector3(-.28,.30,0),'915 MHz TELEMETRY','companion / link','#69baff');
anchor(new THREE.Vector3(-.17,.30,.12),'ESC ×4','one controller per motor','#39e6b8');
anchor(new THREE.Vector3(0,-.12,.02),'PDB / POWER MODULE','battery distribution','#ffb34c');
anchor(new THREE.Vector3(.23,-.04,.02),'PAYLOAD SERVO','release actuator','#ff6878');
anchor(new THREE.Vector3(0,-.16,.26),'HEALTH KIT BAY','payload','#ff6878');
function connect(a,b,color){const g=new THREE.BufferGeometry().setFromPoints([a,b]);anchors.add(new THREE.Line(g,new THREE.LineBasicMaterial({color,transparent:true,opacity:.45})))}
connect(new THREE.Vector3(-.17,.30,.12),new THREE.Vector3(0,.275,0),0x69baff);connect(new THREE.Vector3(0,.275,0),new THREE.Vector3(-.17,.30,.12),0x39e6b8);connect(new THREE.Vector3(0,-.12,.02),new THREE.Vector3(-.17,.30,.12),0xffb34c);connect(new THREE.Vector3(0,-.12,.02),new THREE.Vector3(-.17,.30,.12),0xffb34c);connect(new THREE.Vector3(0,.275,0),new THREE.Vector3(-.28,.30,0),0x39e6b8);
connect(new THREE.Vector3(0,.275,0),new THREE.Vector3(.23,-.04,.02),0xff6878);
function setExploded(on){for(const o of liveParts){const t=on?o.userData.ex:o.userData.base;if(t)o.position.copy(t)}$('assemble').textContent=on?'ASSEMBLE DRONE':'ASSEMBLED VIEW';}
function markSteps(s){const map={s1:s!=='IDLE',s2:['POWER_UP','FC_BOOT','GPS_LOCK','ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(s),s3:['GPS_LOCK','ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(s),s4:['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(s),s5:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(s),s6:['ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(s),s7:['DELIVERING','RTL','LANDING'].includes(s),s8:['RTL','LANDING'].includes(s)};Object.entries(map).forEach(([id,v])=>$(id).className='step '+(v?'done':''))}
function apply(d){state=String(d.state||'IDLE').toUpperCase();rpm=Number(d.motor_rpm||0);$('state').textContent=state;$('mission').textContent=d.mission_id||'—';$('speed').textContent=Number(d.speed_ms||0).toFixed(1)+' m/s';$('alt').textContent=Number(d.altitude_m||0).toFixed(1)+' m';$('rpm').textContent=Math.round(rpm);const powered=state!=='IDLE';const armed=['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(state);$('battery').textContent=powered?'ON':'STANDBY';$('fc').textContent=powered?'BOOTED':'OFF';$('gps').textContent=armed?'LOCKED':'NO FIX';$('telem').textContent=powered?'ONLINE':'OFFLINE';$('esc').textContent=armed?'ACTIVE':'OFF';$('ctrl').textContent=armed?'PWM / DShot':'STANDBY';$('motorState').textContent=armed?'SPINNING':'OFF';$('servo').textContent=state==='DELIVERING'?'OPEN':'CLOSED';$('kit').textContent=state==='DELIVERING'?'RELEASED':'SECURED';markSteps(state);if(state!==lastState){log('STATE → '+state);lastState=state}}
async function poll(){try{const r=await fetch('/drone_state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);apply(await r.json());setStatus('LIVE — /drone_state synchronized');}catch(e){setStatus('Hub state unavailable: '+e.message,true)}finally{setTimeout(poll,800)}}
const demoStates=['DISTRESS','POWER_UP','FC_BOOT','GPS_LOCK','ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','IDLE'];
function runDemo(){clearInterval(demoTimer);let i=0;apply({state:demoStates[i],mission_id:'WEB-DEMO',speed_ms:0,altitude_m:0,motor_rpm:0});demoTimer=setInterval(()=>{i++;if(i>=demoStates.length){clearInterval(demoTimer);return}const s=demoStates[i];const rpm=['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(s)?5000:0;const alt=s==='TAKEOFF'?4:(['ENROUTE','HOVERING','DELIVERING','RTL'].includes(s)?15:0);const speed=['ENROUTE','RTL'].includes(s)?15:0;apply({state:s,mission_id:'WEB-DEMO',speed_ms:speed,altitude_m:alt,motor_rpm:rpm});},1300)}
$('live').onclick=()=>{setStatus('Following live hub state…');poll()};$('test').onclick=async()=>{const b=$('test');b.disabled=true;setStatus('DISTRESS received — powering systems automatically…');log('DISTRESS → automatic startup');try{const r=await fetch('/node-alert?node=WEB-F450-REAL&lat=21.128&lon=79.047&event=1&conf=0.99&pir=1&light=30');if(!r.ok)throw Error('HTTP '+r.status);setStatus('Hub accepted distress — waiting for flight state');}catch(e){setStatus('Hub trigger unavailable — running local hardware demo',true)}runDemo();setTimeout(()=>b.disabled=false,1200)};
$('labelsBtn').onclick=()=>{labelsOn=!labelsOn;labels.domElement.style.display=labelsOn?'block':'none';$('labelsBtn').textContent=labelsOn?'HIDE LABELS':'SHOW LABELS'};$('assemble').onclick=()=>setExploded(false);function resize(){const r=$('view').getBoundingClientRect();cam.aspect=r.width/r.height;cam.updateProjectionMatrix();renderer.setSize(r.width,r.height,false);labels.setSize(r.width,r.height)}addEventListener('resize',resize);resize();
const clock=new THREE.Clock();function animate(){requestAnimationFrame(animate);const dt=clock.getDelta();const spin=Math.max(0,rpm)*Math.PI*2/60*dt;for(const r of rotors)r.rotation.z+=spin*(r.userData.dir||1);controls.update();renderer.render(scene,cam);labels.render(scene,cam)}animate();poll();
</script></body></html>'''
