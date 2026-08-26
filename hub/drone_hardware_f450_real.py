"""Real F450 mesh hardware visualization for VanniKawachh."""
from fastapi.responses import HTMLResponse


def attach(app):
    @app.get("/drone-hardware", response_class=HTMLResponse)
    def drone_hardware_page():
        return HTML


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanniKawachh · Real F450 Hardware</title>
<style>
:root{--bg:#050a0f;--line:#294653;--txt:#edf7fa;--muted:#90a7b4;--power:#ffb34c;--data:#69baff;--ctrl:#39e6b8;--pay:#ff6878}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--txt);font:12px Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 430px;height:100vh}#view{position:relative;min-width:0}#c{width:100%;height:100%;display:block}
.top{position:absolute;z-index:10;left:13px;right:13px;top:13px;display:flex;justify-content:space-between;pointer-events:none}.pill{background:#07131eed;border:1px solid var(--line);border-radius:999px;padding:9px 12px}.pill b{color:#fff}
#labels{position:absolute;inset:0;pointer-events:none}.tag{padding:5px 7px;border:1px solid currentColor;border-radius:6px;background:#061017ee;font-size:10px;white-space:nowrap}.tag small{display:block;color:#a5bac4;font-size:8px;margin-top:2px}
#side{overflow:auto;background:#07121bf8;border-left:1px solid var(--line);padding:13px}.title{font-size:22px;font-weight:900}.sub,.note{font-size:10px;color:var(--muted);line-height:1.55}.card{background:#0b1821;border:1px solid var(--line);border-radius:12px;padding:11px;margin:9px 0}.lab{font-size:10px;letter-spacing:.1em;color:var(--muted);font-weight:900}.big{font-size:27px;font-weight:900}.ok{color:var(--ctrl)}.warn{color:var(--power)}.row{display:flex;justify-content:space-between;gap:10px;margin:7px 0}.val{font-weight:900;text-align:right}.seq{display:grid;gap:4px}.step{padding:7px 9px;border:1px solid #1d3440;border-radius:8px;color:#667f8c}.step.done{background:#0c211b;color:#b0f4e2;border-color:#2a705e}.step.active{background:#231a0f;color:#ffe0a1;border-color:#936827}.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:3px;align-items:center}.node{padding:7px 3px;border:1px solid #294653;border-radius:7px;text-align:center;font-size:8px}.node.active{border-color:var(--ctrl);box-shadow:0 0 14px #39e6b833}.btns{display:grid;grid-template-columns:1fr 1fr;gap:7px}.btn{border:1px solid var(--line);border-radius:8px;padding:10px;background:#122532;color:#fff;font-weight:900;cursor:pointer}.btn.primary{background:#0c3026;border-color:#2c705e}.btn.warn{background:#2a2113;border-color:#75552b}.btn:disabled{opacity:.45}.status{padding:9px;border:1px solid var(--line);border-radius:8px;background:#061016;font-size:10px;margin:8px 0}.good{border-color:#2a705e;color:#b4f5e4}.bad{border-color:#913443;color:#ffc0c7}.log{height:88px;overflow:auto;background:#051017;border:1px solid #17303d;border-radius:7px;padding:6px;font:9px/1.45 monospace;color:#8fb9c7}
@media(max-width:900px){#app{grid-template-columns:1fr}#side{position:absolute;z-index:50;right:0;top:0;bottom:0;width:min(430px,96vw);box-shadow:-20px 0 50px #000c}}
</style></head>
<body>
<div id="app"><section id="view"><div class="top"><div class="pill"><b>VANNIKAWACHH</b> · REAL F450 / PIXHAWK HARDWARE</div><div class="pill">SOURCE: <b id="source">LOADING F450 MESHES</b></div></div><canvas id="c"></canvas><div id="labels"></div></section>
<aside id="side"><div class="title">Real F450 Hardware Assembly</div><div class="sub">The aircraft body uses real F450 Gazebo mesh assets. Electronics and signal links are overlaid for the proposed Pixhawk build.</div>
<div class="card"><div class="lab">LIVE MISSION</div><div id="state" class="big ok">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="val">—</span></div><div class="row"><span>Speed</span><span id="speed" class="val">0.0 m/s</span></div><div class="row"><span>Altitude</span><span id="alt" class="val">0.0 m</span></div><div class="row"><span>Motor RPM</span><span id="rpm" class="val">0</span></div></div>
<div class="card"><div class="lab">F450 BUILD</div><div class="row"><span>Frame</span><span class="val">Flame Wheel F450</span></div><div class="row"><span>Motors</span><span class="val">DJI 2312E 960KV ×4</span></div><div class="row"><span>Props</span><span class="val">F450 prop meshes ×4</span></div><div class="row"><span>Flight controller</span><span class="val">Pixhawk 2.1 / CubeOrange</span></div><div class="row"><span>GPS</span><span class="val">F9P RTK + compass</span></div></div>
<div class="card"><div class="lab">POWER / CONTROL / PAYLOAD</div><div class="row"><span>LiPo → PDB → ESC ×4</span><span id="powerState" class="val" style="color:var(--power)">READY</span></div><div class="row"><span>ESC → motors → props</span><span id="motorState" class="val">OFF</span></div><div class="row"><span>ESP32 → Hub → companion</span><span id="link" class="val" style="color:var(--data)">STANDBY</span></div><div class="row"><span>Pixhawk → ESC control</span><span id="ctrl" class="val" style="color:var(--ctrl)">STANDBY</span></div><div class="row"><span>Servo → health kit</span><span id="servo" class="val" style="color:var(--pay)">CLOSED</span></div></div>
<div class="card"><div class="lab">MISSION SEQUENCE</div><div class="seq"><div id="s1" class="step">Distress trigger</div><div id="s2" class="step">Hub / companion command</div><div id="s3" class="step">Pixhawk arm</div><div id="s4" class="step">ESC + rotor spool</div><div id="s5" class="step">Vertical takeoff</div><div id="s6" class="step">Fly / hover at target</div><div id="s7" class="step">Open payload bay</div><div id="s8" class="step">Release health kit</div><div id="s9" class="step">RTL / land</div></div></div>
<div class="card"><div class="lab">SIGNAL CHAIN</div><div class="chain"><div id="n1" class="node">ESP32<br>SENSOR</div><div>→</div><div id="n2" class="node">HUB<br>DISPATCH</div><div>→</div><div id="n3" class="node">PIXHAWK<br>ARDUPILOT</div><div>→</div><div id="n4" class="node">ESC ×4<br>+ SERVO</div></div></div>
<div class="btns"><button id="live" class="btn primary">LIVE HUB</button><button id="test" class="btn">TEST DISTRESS</button><button id="explode" class="btn warn">EXPLODED VIEW</button><button id="assemble" class="btn">ASSEMBLED VIEW</button></div>
<div id="status" class="status">Loading real F450 mesh assembly…</div><div id="log" class="log"></div>
<div class="note">Mesh source: beomsu7/px4-quadrotor-HW-parts custom_f450 Gazebo model.</div>
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
const scene=new THREE.Scene();scene.background=new THREE.Color(0x050a0f);scene.fog=new THREE.Fog(0x050a0f,3,20);
const cam=new THREE.PerspectiveCamera(40,1,.01,100);cam.position.set(1.8,1.3,2.2);
const renderer=new THREE.WebGLRenderer({canvas:$('c'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
const labels=new CSS2DRenderer();labels.domElement.style.position='absolute';labels.domElement.style.inset='0';labels.domElement.style.pointerEvents='none';$('view').appendChild(labels.domElement);
const controls=new OrbitControls(cam,renderer.domElement);controls.enableDamping=true;controls.minDistance=.6;controls.maxDistance=8;controls.target.set(0,.24,0);
scene.add(new THREE.HemisphereLight(0xdbefff,0x11151a,2));const key=new THREE.DirectionalLight(0xffffff,3);key.position.set(3,5,4);scene.add(key);scene.add(new THREE.GridHelper(8,16,0x173640,0x0c242d));
const drone=new THREE.Group();scene.add(drone);const liveParts=[],rotors=[],motors=[];let exploded=false,rpm=0,state='IDLE',lastState='IDLE';
const M={frame:new THREE.MeshStandardMaterial({color:0x2a2f33,metalness:.6,roughness:.28}),red:new THREE.MeshStandardMaterial({color:0xa32934,metalness:.4,roughness:.3}),white:new THREE.MeshStandardMaterial({color:0xe5eaed,metalness:.15,roughness:.3}),black:new THREE.MeshStandardMaterial({color:0x1a1e22,metalness:.55,roughness:.3}),gold:new THREE.MeshStandardMaterial({color:0xb97d20,metalness:.45,roughness:.28}),blue:new THREE.MeshStandardMaterial({color:0x245a78,metalness:.3,roughness:.34}),green:new THREE.MeshStandardMaterial({color:0x16645b,metalness:.15,roughness:.38}),pay:new THREE.MeshStandardMaterial({color:0x8f2936,metalness:.25,roughness:.34})};
function tag(parent,t,s,c){const d=document.createElement('div');d.className='tag';d.style.color=c;d.innerHTML='<b>'+t+'</b><small>'+s+'</small>';parent.add(new CSS2DObject(d))}
function reg(o,ex){o.userData.base=o.position.clone();o.userData.ex=ex.clone();liveParts.push(o)}
function stl(url,mat,cb){new STLLoader().load(url,g=>{const o=new THREE.Mesh(g,mat);o.castShadow=o.receiveShadow=true;cb(o)},undefined,e=>{log('STL load failed');console.error(e);setStatus('Mesh load error',true)})}
function dae(url,cb){new ColladaLoader().load(url,d=>{d.scene.traverse(x=>{if(x.isMesh){x.material=M.white;x.castShadow=x.receiveShadow=true}});cb(d.scene)},undefined,e=>{log('Prop mesh load failed');console.error(e)})}
// Exact real mesh assets from the public Gazebo F450 package.
stl(U.base,M.frame,o=>{drone.add(o);reg(o,new THREE.Vector3(0,1.0,0));tag(o,'F450 FRAME','base_link.stl','#39e6b8')});
stl(U.leg,M.white,o=>{o.position.set(0,.132,0);drone.add(o);reg(o,new THREE.Vector3(0,-.35,-1.8));tag(o,'LANDING GEAR','leg_link.stl','#cfd9de')});
stl(U.battery,M.black,o=>{o.position.set(-.0254,-.0002,.09);drone.add(o);reg(o,new THREE.Vector3(-1.0,-.35,0));tag(o,'BATTERY','battery_link.stl','#ffb34c')});
[[.098,.098,0],[.098,-.098,Math.PI/2],[-.098,-.098,Math.PI],[-.098,.098,-Math.PI/2]].forEach((p,i)=>stl(i%2?U.back:U.front,i<2?M.red:M.white,o=>{o.position.set(p[0],p[1],.171);o.rotation.z=p[2];drone.add(o);reg(o,new THREE.Vector3(p[0]*5,1,p[1]*5));tag(o,'ARM '+(i+1),'real F450 arm mesh',i<2?'#ef5560':'#e9eef0')}));
const mp=[[.15988,-.15988],[-.15988,.15988],[.15988,.15988],[-.15988,-.15988]];
mp.forEach((p,i)=>{stl(U.motor,M.black,o=>{o.position.set(p[0],p[1],.173);drone.add(o);motors.push(o);reg(o,new THREE.Vector3(p[0]*5,1.55,p[1]*5));tag(o,'MOTOR '+(i+1),'motor_link.STL','#39e6b8')});dae(i%2?U.cw:U.ccw,o=>{o.position.set(p[0],p[1],.206);o.scale.setScalar(.55);o.userData.dir=i%2? -1:1;o.userData.base=o.position.clone();o.userData.ex=new THREE.Vector3(p[0]*5,1.7,p[1]*5);drone.add(o);rotors.push(o);tag(o,'PROP '+(i+1),'real Collada mesh','#dce7ed')})});
// Engineering overlays: physical flight-control/power/payload locations.
function box(s,m,pos,title,sub,ex,color){const o=new THREE.Mesh(new THREE.BoxGeometry(...s),m);o.position.copy(pos);o.userData.base=pos.clone();o.userData.ex=ex.clone();o.userData.kind='overlay';drone.add(o);liveParts.push(o);tag(o,title,sub,color);return o}
const fc=box([.36,.06,.24],M.blue,new THREE.Vector3(0,0.27,0),'PIXHAWK / CUBE','ArduPilot FC',new THREE.Vector3(0,1.55,0), '#39e6b8');
const gps=box([.18,.08,.18],M.white,new THREE.Vector3(0,0.48,-.02),'F9P GPS','compass + RTK',new THREE.Vector3(0,2.0,.35),'#69baff');
const telem=box([.22,.06,.11],M.green,new THREE.Vector3(-.28,.30,0),'915 MHz TELEMETRY','companion / link',new THREE.Vector3(-1.7,1.25,.35),'#69baff');
const batt=box([.46,.10,.22],M.black,new THREE.Vector3(0,-.02,0),'LiPo','4S pack',new THREE.Vector3(-1.7,-.5,0),'#ffb34c');
const pdb=box([.26,.05,.18],M.gold,new THREE.Vector3(0,.12,0),'PDB / POWER MODULE','battery distribution',new THREE.Vector3(-1.0,-.15,0),'#ffb34c');
const servo=box([.14,.07,.10],M.pay,new THREE.Vector3(.28,.08,0),'PAYLOAD SERVO','release actuator',new THREE.Vector3(1.7,.5,0),'#ff6878');
const payload=box([.38,.12,.30],M.gold,new THREE.Vector3(0,-.16,0),'HEALTH KIT BAY','payload',new THREE.Vector3(1.7,-.3,.7),'#ff6878');
function setExploded(on){exploded=on;for(const o of liveParts){const t=on?o.userData.ex:o.userData.base;if(t)o.position.copy(t)};$('explode').textContent=on?'ASSEMBLED VIEW':'EXPLODED VIEW'}
function apply(d){state=d.state||'IDLE';rpm=Number(d.motor_rpm||0);$('state').textContent=state;$('source').textContent='REAL F450 GAZEBO MESH';$('mission').textContent=d.mission_id||'—';$('speed').textContent=Number(d.speed_ms||0).toFixed(1)+' m/s';$('alt').textContent=Number(d.altitude_m||0).toFixed(1)+' m';$('rpm').textContent=Math.round(rpm);const active=['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(state);$('powerState').textContent=active?'POWERED':'READY';$('motorState').textContent=active?'RUNNING':'OFF';$('link').textContent=state==='IDLE'?'STANDBY':'ACTIVE';$('ctrl').textContent=active?'PWM / DShot':'STANDBY';$('servo').textContent=state==='DELIVERING'?'OPEN':'CLOSED';$('s1').className='step '+(state!=='IDLE'?'done':'');$('s2').className='step '+(state!=='IDLE'?'done':'');$('s3').className='step '+(active?'done':'');$('s4').className='step '+(active?'done':'');$('s5').className='step '+(['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'].includes(state)?'done':'');$('s6').className='step '+(['ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'].includes(state)?'done':'');$('s7').className='step '+(['DELIVERING','RTL','LANDING','COMPLETED'].includes(state)?'done':'');$('s8').className='step '+(['RTL','LANDING','COMPLETED'].includes(state)?'done':'');$('s9').className='step '+(['RTL','LANDING','COMPLETED'].includes(state)?'done':'');$('n1').className='node '+(state!=='IDLE'?'active':'');$('n2').className='node '+(state!=='IDLE'?'active':'');$('n3').className='node '+(active?'active':'');$('n4').className='node '+(active?'active':'');if(state!==lastState){log('STATE → '+state);lastState=state}}
function poll(){fetch('/drone_state?ts='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(apply).catch(e=>setStatus('Hub error: '+e.message,true)).finally(()=>setTimeout(poll,800))}
$('live').onclick=()=>poll();$('test').onclick=async()=>{const b=$('test');b.disabled=true;setStatus('Sending distress…');try{const r=await fetch('/node-alert?node=WEB-F450-REAL&lat=21.128&lon=79.047&event=1&conf=0.99&pir=1&light=30');if(!r.ok)throw Error('HTTP '+r.status);setStatus('Distress accepted','good');log('DISTRESS → accepted')}catch(e){setStatus('Trigger failed: '+e.message,true);log('TRIGGER ERROR → '+e.message)}finally{setTimeout(()=>b.disabled=false,700)}};$('explode').onclick=()=>setExploded(!exploded);$('assemble').onclick=()=>setExploded(false);
function resize(){const r=$('view').getBoundingClientRect();cam.aspect=r.width/r.height;cam.updateProjectionMatrix();renderer.setSize(r.width,r.height,false);labels.setSize(r.width,r.height)}addEventListener('resize',resize);resize();poll();const clock=new THREE.Clock();function animate(){requestAnimationFrame(animate);const dt=clock.getDelta();const spin=Math.max(0,rpm)*Math.PI*2/60*dt;for(const r of rotors)r.rotation.z+=spin*(r.userData.dir||1);controls.update();renderer.render(scene,cam);labels.render(scene,cam)}animate();
</script></body></html>'''
