from base64 import b64decode
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi.responses import HTMLResponse, Response


ASSET_DIR = "custom_f450/meshes/"
ASSETS = {
    "base_link.stl": "model/stl",
    "front_arm_link.stl": "model/stl",
    "back_arm_link.STL": "model/stl",
    "motor_link.STL": "model/stl",
    "leg_link.stl": "model/stl",
    "battery_link.stl": "model/stl",
    "iris_prop_cw.dae": "model/collada+xml",
    "iris_prop_ccw_centered.dae": "model/collada+xml",
}
ASSET_CACHE = {}


def _get_asset(name: str):
    if name not in ASSETS:
        return None
    if name in ASSET_CACHE:
        return ASSET_CACHE[name]
    local_path = Path(__file__).with_name("assets") / "f450" / name
    if local_path.is_file():
        data = local_path.read_bytes()
        ASSET_CACHE[name] = data
        return data
    path = ASSET_DIR + quote(name)
    urls = [
        "https://cdn.jsdelivr.net/gh/beomsu7/px4-quadrotor-HW-parts@main/" + path,
        "https://raw.githubusercontent.com/beomsu7/px4-quadrotor-HW-parts/main/" + path,
    ]
    for url in urls:
        try:
            request = Request(url, headers={"User-Agent": "VanniKawachh-F450/5.0"})
            with urlopen(request, timeout=20) as response:
                data = response.read()
            if data:
                ASSET_CACHE[name] = data
                return data
        except Exception:
            continue
    request = Request(
        "https://api.github.com/repos/beomsu7/px4-quadrotor-HW-parts/contents/" + path,
        headers={
            "User-Agent": "VanniKawachh-F450/5.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = b64decode(payload["content"])
    ASSET_CACHE[name] = data
    return data


def attach(app):
    @app.get("/drone-assets/{name}", include_in_schema=False)
    def asset(name: str):
        try:
            data = _get_asset(name)
            if data is None:
                return Response(status_code=404)
            return Response(
                data,
                media_type=ASSETS[name],
                headers={"Cache-Control": "public,max-age=3600"},
            )
        except Exception as exc:
            return Response(str(exc), status_code=502, media_type="text/plain")

    @app.get("/drone-hardware", response_class=HTMLResponse)
    def page():
        return HTML


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanniKawachh · DJI F450 Hardware</title>
<style>
:root{--bg:#050a0f;--panel:#07141d;--line:#294653;--text:#eef7fa;--muted:#91a8b5;--green:#39e6b8;--blue:#69baff;--amber:#ffb34c;--red:#ff6878}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:12px Segoe UI,Arial,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 405px;height:100vh}#view{position:relative;min-width:0;background:#050a0f}#c{width:100%;height:100%;display:block;cursor:grab}#c.drag{cursor:grabbing}
.top{position:absolute;z-index:10;left:14px;right:14px;top:14px;display:flex;justify-content:space-between;pointer-events:none}.pill{padding:9px 12px;border:1px solid var(--line);border-radius:999px;background:#07131eee}.pill b{color:#fff}.hud{position:absolute;z-index:10;left:14px;bottom:14px;padding:9px 12px;border:1px solid #2a705e;border-radius:8px;background:#071a16ee;color:#b4f5e4;font:11px Consolas,monospace}.flow{position:absolute;z-index:10;left:14px;bottom:55px;padding:8px 11px;border:1px solid #356a89;border-radius:8px;background:#07131eee;color:#b9dcf5;font:10px Consolas,monospace;display:none}
#labels{position:absolute;inset:0;pointer-events:none}#labels:not(.exploded) .tag{display:none}.tag{padding:5px 7px;border:1px solid currentColor;border-radius:6px;background:#061017f2;box-shadow:0 4px 14px #0008;white-space:nowrap;font-size:10px}.tag small{display:block;margin-top:2px;color:#a9bbc4;font-size:8px}
#side{overflow:auto;padding:14px;background:var(--panel);border-left:1px solid var(--line)}.title{font-size:22px;font-weight:900}.sub,.note{color:var(--muted);font-size:10px;line-height:1.5}.card{margin:9px 0;padding:11px;border:1px solid var(--line);border-radius:11px;background:linear-gradient(180deg,#0d1d27,#08131b)}.lab{color:var(--muted);font-size:10px;font-weight:900;letter-spacing:.1em}.big{margin:2px 0;font-size:27px;font-weight:900;color:var(--green)}.row{display:flex;justify-content:space-between;gap:10px;margin:7px 0}.val{font-weight:900;text-align:right}.amber{color:var(--amber)}.blue{color:var(--blue)}.red{color:var(--red)}.seq{display:grid;gap:4px}.step{padding:7px 9px;border:1px solid #1d3440;border-radius:8px;color:#667f8c}.step.done{background:#0c211b;color:#b0f4e2;border-color:#2a705e}.step.active{background:#231a0f;color:#ffe0a1;border-color:#936827}.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:3px;align-items:center}.node{padding:7px 3px;border:1px solid var(--line);border-radius:7px;text-align:center;font-size:8px}.node.active{border-color:var(--green);box-shadow:0 0 14px #39e6b844}.btns{display:grid;grid-template-columns:1fr 1fr;gap:7px}.btn{padding:10px;border:1px solid var(--line);border-radius:8px;background:#122532;color:#fff;font-weight:900;cursor:pointer}.btn.primary{background:#0c3026;border-color:#2c705e}.btn.warn{background:#2a2113;border-color:#75552b}.btn:disabled{opacity:.45}.status{margin:8px 0;padding:9px;border:1px solid var(--line);border-radius:8px;background:#061016;font-size:10px}.good{border-color:#2a705e;color:#b4f5e4}.bad{border-color:#913443;color:#ffc0c7}.log{height:90px;overflow:auto;padding:6px;border:1px solid #17303d;border-radius:7px;background:#051017;color:#8fb9c7;font:9px/1.45 Consolas,monospace}
@media(max-width:900px){#app{grid-template-columns:1fr}#side{position:absolute;z-index:20;right:0;top:0;bottom:0;width:min(405px,96vw);box-shadow:-20px 0 50px #000c}}
</style>
</head>
<body>
<div id="app"><section id="view"><div class="top"><div class="pill"><b>VANNIKAWACHH</b> · REAL DJI F450 HARDWARE</div><div class="pill">SOURCE: <b id="source">LOADING MESHES</b></div></div><canvas id="c"></canvas><div id="labels"></div><div id="flow"></div><div id="hud">IDLE · 0 RPM · 0.0 m AGL</div></section>
<aside id="side"><div class="title">F450 Hardware in Motion</div><div class="sub">The airframe uses the real F450 Gazebo mesh package: frame, arms, motors, landing gear, battery and four propellers. Toggle the exploded engineering view to see the physical relationship and the live signal paths without hiding the actual mesh.</div>
<div class="card"><div class="lab">LIVE MISSION</div><div id="state" class="big">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="val">—</span></div><div class="row"><span>Speed</span><span id="speed" class="val">0.0 m/s</span></div><div class="row"><span>Altitude AGL</span><span id="alt" class="val">0.0 m</span></div><div class="row"><span>Motor RPM</span><span id="rpm" class="val">0</span></div></div>
<div class="card"><div class="lab">PHYSICAL POWER PATH</div><div class="row"><span>LiPo → PDB / power module</span><span class="val amber">POWER</span></div><div class="row"><span>PDB → ESC ×4</span><span id="esc" class="val">READY</span></div><div class="row"><span>ESC → BLDC motors ×4</span><span id="motors" class="val">OFF</span></div><div class="row"><span>Motors → propellers</span><span id="props" class="val">STOPPED</span></div></div>
<div class="card"><div class="lab">CONTROL + PAYLOAD</div><div class="row"><span>GPS + compass → Pixhawk</span><span class="val blue">DATA</span></div><div class="row"><span>ESP32 → hub → companion</span><span id="link" class="val blue">STANDBY</span></div><div class="row"><span>Pixhawk → ESC control</span><span id="ctrl" class="val">STANDBY</span></div><div class="row"><span>Servo → health-kit bay</span><span id="servo" class="val red">CLOSED</span></div></div>
<div class="card"><div class="lab">MISSION SEQUENCE</div><div class="seq"><div id="s1" class="step">Distress received</div><div id="s2" class="step">Hub / companion command</div><div id="s3" class="step">Pixhawk arms</div><div id="s4" class="step">ESC + rotor spool</div><div id="s5" class="step">Vertical takeoff</div><div id="s6" class="step">Fly / hover at target</div><div id="s7" class="step">Open payload bay</div><div id="s8" class="step">Release health kit</div><div id="s9" class="step">RTL / land</div></div></div>
<div class="card"><div class="lab">SIGNAL CHAIN</div><div class="chain"><div id="n1" class="node">ESP32<br>SENSOR</div><div>→</div><div id="n2" class="node">HUB<br>DISPATCH</div><div>→</div><div id="n3" class="node">PIXHAWK<br>ARDUPILOT</div><div>→</div><div id="n4" class="node">ESC ×4<br>+ SERVO</div></div></div>
<div class="btns"><button id="live" class="btn primary">LIVE HUB</button><button id="test" class="btn">TEST DISTRESS</button><button id="explode" class="btn warn">EXPLODE VIEW</button><button id="assemble" class="btn">ASSEMBLE</button></div><div id="status" class="status good">Loading real F450 meshes…</div><div class="note">Drag the aircraft to rotate it. Shift-drag pans. Mouse wheel zooms. Exploded mode separates every real mesh and reveals the engineering signal/power routes. Test distress uses the same `/node-alert` path as the sensing node.</div><div id="log" class="log"></div></aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as T from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {CSS2DRenderer,CSS2DObject} from 'three/addons/renderers/CSS2DRenderer.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
import {ColladaLoader} from 'three/addons/loaders/ColladaLoader.js';

const $=id=>document.getElementById(id),U='/drone-assets/';
const scene=new T.Scene();scene.background=new T.Color(0x050a0f);scene.fog=new T.Fog(0x050a0f,3,18);
const cam=new T.PerspectiveCamera(40,1,.01,100);const renderer=new T.WebGLRenderer({canvas:$('c'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=T.SRGBColorSpace;renderer.shadowMap.enabled=true;
const labels=new CSS2DRenderer();labels.domElement.id='label-layer';labels.domElement.style.position='absolute';labels.domElement.style.inset='0';labels.domElement.style.pointerEvents='none';$('labels').appendChild(labels.domElement);
const controls=new OrbitControls(cam,renderer.domElement);controls.enableDamping=true;controls.enablePan=true;controls.rotateSpeed=.72;controls.zoomSpeed=.85;controls.minDistance=.55;controls.maxDistance=8;
scene.add(new T.HemisphereLight(0xdbefff,0x11151a,2.2));const key=new T.DirectionalLight(0xffffff,3.4);key.position.set(3,5,4);key.castShadow=true;scene.add(key);const fill=new T.DirectionalLight(0x5ba8d5,1.2);fill.position.set(-4,2,-3);scene.add(fill);scene.add(new T.GridHelper(8,16,0x173640,0x0c242d));
const drone=new T.Group();scene.add(drone);const overlay=new T.Group();drone.add(overlay);const parts=[],props=[],anchors=[],routes=[],pulses=[];let loaded=0,failed=0,exploded=false,rpm=0,state='IDLE',lastState='IDLE',currentAltitude=0,targetAltitude=0;
const mats={frame:new T.MeshStandardMaterial({color:0x30363a,metalness:.68,roughness:.28}),red:new T.MeshStandardMaterial({color:0xa32934,metalness:.4,roughness:.3}),white:new T.MeshStandardMaterial({color:0xdfe7ea,metalness:.12,roughness:.34}),black:new T.MeshStandardMaterial({color:0x171c20,metalness:.6,roughness:.28})};
const log=m=>{const e=$('log');e.innerHTML+='<div>'+new Date().toLocaleTimeString()+' · '+m+'</div>';e.scrollTop=e.scrollHeight};
const status=(m,bad=false)=>{$('status').textContent=m;$('status').className='status '+(bad?'bad':'good')};
function tag(parent,title,sub,color){const el=document.createElement('div');el.className='tag';el.style.color=color;el.innerHTML='<b>'+title+'</b><small>'+sub+'</small>';parent.add(new CSS2DObject(el))}
function register(o,base,ex){o.position.copy(base);o.userData.base=base.clone();o.userData.ex=ex.clone();parts.push(o)}
function stl(file,material,base,rotation,ex,title,color){new STLLoader().load(U+file,g=>{const mesh=new T.Mesh(g,material);mesh.rotation.set(...rotation);mesh.castShadow=mesh.receiveShadow=true;register(mesh,new T.Vector3(...base),new T.Vector3(...ex));drone.add(mesh);tag(mesh,title,file,color);loaded++;ready()},undefined,()=>{failed++;log('Mesh failed: '+file);ready()})}
function prop(file,base,ex,dir,index){new ColladaLoader().load(U+file,d=>{d.scene.traverse(o=>{if(o.isMesh){o.material=mats.white;o.castShadow=o.receiveShadow=true}});d.scene.position.set(...base);d.scene.userData.base=new T.Vector3(...base);d.scene.userData.ex=new T.Vector3(...ex);d.scene.userData.dir=dir;drone.add(d.scene);parts.push(d.scene);props.push(d.scene);tag(d.scene,'PROP '+index,'real Collada mesh','#dce7ed');loaded++;ready()},undefined,()=>{failed++;log('Prop failed: '+file);ready()})}
function makeAnchor(base,ex,title,sub,color){const g=new T.Group();g.position.set(...base);g.userData.base=new T.Vector3(...base);g.userData.ex=new T.Vector3(...ex);g.add(new T.Mesh(new T.TorusGeometry(.055,.009,8,24),new T.MeshBasicMaterial({color,transparent:true,opacity:.8})));tag(g,title,sub,color);overlay.add(g);anchors.push(g);return g}
function connect(a,b,color,type){const line=new T.Line(new T.BufferGeometry(),new T.LineBasicMaterial({color,transparent:true,opacity:.18}));line.userData={a:a.userData?.base||a,b:b.userData?.base||b,aEx:a.userData?.ex,bEx:b.userData?.ex,type};overlay.add(line);routes.push(line);return line}
function updateRoutes(){routes.forEach(line=>{const a=exploded?(line.userData.aEx||line.userData.a):line.userData.a;const b=exploded?(line.userData.bEx||line.userData.b):line.userData.b;line.geometry.setFromPoints([a,b]);line.material.opacity=exploded?.56:.12})}
function pulse(a,b,color){const p=new T.Mesh(new T.SphereGeometry(.035,10,10),new T.MeshBasicMaterial({color}));p.userData={aBase:a.userData?.base||a,bBase:b.userData?.base||b,aEx:a.userData?.ex,bEx:b.userData?.ex,t:Math.random(),speed:.55+Math.random()*.25};overlay.add(p);pulses.push(p)}
function makeEngineeringOverlay(){const sensor=makeAnchor([-1.05,.58,.5],[-2.0,1.3,1.1],'ESP32 SENSOR','distress uplink','#69baff');const hub=makeAnchor([-.58,.5,.43],[-1.15,1.7,.95],'HUB DISPATCH','verified alert','#69baff');const fc=makeAnchor([0,0,.37],[0,2.0,1.1],'PIXHAWK / CUBE','ArduPilot flight controller','#39e6b8');const pdb=makeAnchor([-.08,-.1,.13],[-1.2,.25,.45],'PDB / POWER','battery distribution','#ffb34c');const esc=makeAnchor([.3,.05,.35],[1.15,1.4,.95],'ESC ×4','one controller per motor','#39e6b8');const servo=makeAnchor([.25,-.08,.2],[1.45,.25,.8],'PAYLOAD SERVO','health-kit release','#ff6878');connect(sensor,hub,0x69baff,'data');connect(hub,fc,0x69baff,'data');connect(fc,esc,0x39e6b8,'control');connect(pdb,esc,0xffb34c,'power');connect(fc,servo,0xff6878,'payload');pulse(sensor,hub,0x69baff);pulse(hub,fc,0x69baff);pulse(fc,esc,0x39e6b8);pulse(pdb,esc,0xffb34c);pulse(fc,servo,0xff6878);updateRoutes()}
function ready(){if(loaded+failed!==15)return;const box=new T.Box3().setFromObject(drone),center=box.getCenter(new T.Vector3()),size=box.getSize(new T.Vector3()),max=Math.max(size.x,size.y,size.z)||1;drone.position.sub(center);cam.position.set(max*1.75,max*1.35,max*1.85);controls.target.set(0,0,0);controls.update();$('source').textContent=failed?'F450 PARTIAL':'REAL F450 MESH';status(failed?'F450 loaded with '+failed+' missing asset(s)':'All 15 real F450 mesh assets loaded');log('F450 assembly ready: '+loaded+'/15 real assets');makeEngineeringOverlay();setExploded(false)}
function setExploded(on){exploded=!!on;parts.forEach(o=>o.position.copy(exploded?o.userData.ex:o.userData.base));anchors.forEach(o=>o.position.copy(exploded?o.userData.ex:o.userData.base));overlay.visible=exploded;$('labels').classList.toggle('exploded',exploded);updateRoutes();$('explode').textContent=exploded?'ASSEMBLE VIEW':'EXPLODE VIEW';status(exploded?'Exploded engineering view: meshes + signal paths visible':'Assembled F450 view: propulsion ready')}
stl('base_link.stl',mats.frame,[0,0,0],[0,0,0],[0,0,.78],'F450 FRAME','#39e6b8');
stl('leg_link.stl',mats.white,[0,.132,0],[0,0,0],[0,-.68,-.75],'LANDING GEAR','#dfe5e8');
stl('battery_link.stl',mats.black,[-.025,-.0002,.09],[0,0,0],[-.74,-.38,.18],'BATTERY','#ffb34c');
[[.098,.098,0],[.098,-.098,0],[-.098,-.098,Math.PI],[-.098,.098,Math.PI]].forEach((p,i)=>stl(i%2?'back_arm_link.STL':'front_arm_link.stl',i<2?mats.red:mats.white,[p[0],p[1],.171],[0,0,p[2]],[p[0]*5,p[1]*5,.92],'ARM '+(i+1),i<2?'#ef6570':'#e6edf0'));
[[.15988,-.15988],[-.15988,.15988],[.15988,.15988],[-.15988,-.15988]].forEach((p,i)=>{stl('motor_link.STL',mats.black,[p[0],p[1],.173],[0,0,0],[p[0]*5,p[1]*5,.98],'MOTOR '+(i+1),'#8de0cd');prop(i%2?'iris_prop_cw.dae':'iris_prop_ccw_centered.dae',[p[0],p[1],.206],[p[0]*5,p[1]*5,1.12],i%2?-1:1,i+1)});
function markSteps(s){const done={s1:['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'],s2:['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'],s3:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'],s4:['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'],s5:['ENROUTE','HOVERING','DELIVERING','RTL','LANDING'],s6:['HOVERING','DELIVERING','RTL','LANDING','COMPLETED'],s7:['DELIVERING','RTL','LANDING','COMPLETED'],s8:['RTL','LANDING','COMPLETED'],s9:['RTL','LANDING','COMPLETED']};Object.entries(done).forEach(([id,states])=>$(id).className='step '+(states.includes(s)?'done':''));const active={ARMING:'s3',TAKEOFF:'s4',ENROUTE:'s6',HOVERING:'s6',DELIVERING:'s7',RTL:'s9',LANDING:'s9'}[s];if(active)$(active).className='step active'}
function apply(d){state=String(d?.state||'IDLE').toUpperCase();rpm=Number(d?.motor_rpm||0);targetAltitude=Math.max(0,Number(d?.altitude_m||0));$('state').textContent=state;$('mission').textContent=d?.mission_id||'—';$('speed').textContent=Number(d?.speed_ms||0).toFixed(1)+' m/s';$('alt').textContent=targetAltitude.toFixed(1)+' m';const active=['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(state),powered=state!=='IDLE'&&state!=='COMPLETED'&&state!=='FAILED';$('rpm').textContent=Math.round(active?Math.max(rpm,state==='ARMING'?1800:4300):rpm);$('esc').textContent=active?'4 ACTIVE':'READY';$('motors').textContent=active?'RUNNING':'OFF';$('props').textContent=active?'ROTATING':'STOPPED';$('link').textContent=powered?'ACTIVE':'STANDBY';$('ctrl').textContent=active?'PWM / DShot':'STANDBY';$('servo').textContent=state==='DELIVERING'?'OPEN':'CLOSED';['n1','n2','n3','n4'].forEach(id=>$(id).classList.remove('active'));if(powered){$('n1').classList.add('active');$('n2').classList.add('active')}if(active)$('n3').classList.add('active');if(['DELIVERING','RTL','LANDING','COMPLETED'].includes(state))$('n4').classList.add('active');markSteps(state);if(state!==lastState){log('STATE → '+state);lastState=state}const flowActive=powered;$('flow').style.display=flowActive?'block':'none';$('flow').textContent=flowActive?'LIVE SIGNAL  ESP32 → HUB → PIXHAWK → ESC ×4 → MOTORS  ·  '+state:''}
async function poll(){try{const r=await fetch('/drone_state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);apply(await r.json());status('LIVE HUB synchronized')}catch(e){status('Hub telemetry unavailable: '+e.message,true)}setTimeout(poll,800)}
async function trigger(){const button=$('test');button.disabled=true;status('Distress sent → powering F450 systems');log('TEST DISTRESS → /node-alert');try{const r=await fetch('/node-alert?node=WEB-F450-HARDWARE&lat=21.128&lon=79.047&event=1&conf=0.99&pir=1&light=30',{cache:'no-store'});const payload=await r.json();if(!r.ok||payload.ok===false)throw Error(payload.error||'hub rejected the alert');if(!payload.dispatched)throw Error('hub accepted the alert but did not dispatch a drone');log('HUB ACCEPTED DISTRESS · '+(payload.mission_id||'mission started'));setExploded(true);status('Distress accepted → live signal path active');await poll()}catch(e){status('Distress trigger failed: '+e.message,true);log('TRIGGER ERROR → '+e.message)}finally{setTimeout(()=>button.disabled=false,700)}}
function resize(){const r=$('view').getBoundingClientRect();cam.aspect=r.width/r.height;cam.updateProjectionMatrix();renderer.setSize(r.width,r.height,false);labels.setSize(r.width,r.height)}
$('live').onclick=()=>{status('Following live hub state');poll()};$('test').onclick=trigger;$('explode').onclick=()=>setExploded(!exploded);$('assemble').onclick=()=>setExploded(false);addEventListener('resize',resize);resize();poll();
let lastFrame=performance.now();function loop(now){requestAnimationFrame(loop);const dt=Math.min(.05,(now-lastFrame)/1000);lastFrame=now;const active=['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(state),effectiveRpm=active?Math.max(rpm,state==='ARMING'?1800:4300):0;currentAltitude+=(targetAltitude-currentAltitude)*Math.min(1,dt*4);drone.position.y=Math.min(currentAltitude*.035,1.8);const spin=effectiveRpm*Math.PI*2/60*dt;props.forEach(p=>p.rotation.z+=spin*(p.userData.dir||1));pulses.forEach(p=>{p.userData.t=(p.userData.t+p.userData.speed*dt)%1;const a=exploded?(p.userData.aEx||p.userData.aBase):p.userData.aBase;const b=exploded?(p.userData.bEx||p.userData.bBase):p.userData.bBase;p.position.lerpVectors(a,b,p.userData.t);p.visible=active});$('hud').textContent=state+' · '+Math.round(effectiveRpm)+' RPM · '+currentAltitude.toFixed(1)+' m AGL';controls.update();renderer.render(scene,cam);labels.render(scene,cam)}requestAnimationFrame(loop);
</script>
</body></html>'''
