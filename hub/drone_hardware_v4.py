from fastapi.responses import HTMLResponse, Response
from urllib.request import Request, urlopen
from urllib.parse import quote
import json, base64

ASSET_DIR = "custom_f450/meshes/"
ASSETS = {
    "base_link.stl":"model/stl", "front_arm_link.stl":"model/stl", "back_arm_link.STL":"model/stl",
    "motor_link.STL":"model/stl", "leg_link.stl":"model/stl", "battery_link.stl":"model/stl",
    "iris_prop_cw.dae":"model/collada+xml", "iris_prop_ccw_centered.dae":"model/collada+xml",
}
CACHE = {}

def _get_asset(name: str):
    if name not in ASSETS:
        return None
    if name in CACHE:
        return CACHE[name]
    paths = [
        "https://cdn.jsdelivr.net/gh/beomsu7/px4-quadrotor-HW-parts@main/" + ASSET_DIR + quote(name),
        "https://raw.githubusercontent.com/beomsu7/px4-quadrotor-HW-parts/main/" + ASSET_DIR + quote(name),
    ]
    for url in paths:
        try:
            req = Request(url, headers={"User-Agent":"VanniKawachh-F450/4.0","Accept":"*/*"})
            with urlopen(req, timeout=20) as r:
                data = r.read()
            if data:
                CACHE[name] = data
                return data
        except Exception:
            pass
    api = "https://api.github.com/repos/beomsu7/px4-quadrotor-HW-parts/contents/" + ASSET_DIR + quote(name)
    req = Request(api, headers={"User-Agent":"VanniKawachh-F450/4.0","Accept":"application/vnd.github+json"})
    with urlopen(req, timeout=20) as r:
        payload = json.loads(r.read().decode("utf-8"))
    data = base64.b64decode(payload["content"])
    CACHE[name] = data
    return data

def attach(app):
    @app.get('/drone-assets/{name}', include_in_schema=False)
    def asset(name: str):
        try:
            data = _get_asset(name)
            if data is None:
                return Response(status_code=404)
            return Response(data, media_type=ASSETS[name], headers={"Cache-Control":"public,max-age=3600"})
        except Exception as exc:
            return Response(str(exc), status_code=502, media_type='text/plain')

    @app.get('/drone-hardware', response_class=HTMLResponse)
    def page():
        return HTML

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VanniKawachh F450 Hardware</title>
<style>html,body{margin:0;height:100%;overflow:hidden;background:#061017;color:#eef5f7;font:12px Segoe UI,Arial}#app{display:grid;grid-template-columns:minmax(0,1fr) 370px;height:100vh}#view{position:relative;min-width:0}#c{width:100%;height:100%;display:block;cursor:grab}#c.drag{cursor:grabbing}.pill,.hud{position:absolute;z-index:3;top:14px;padding:9px 12px;border:1px solid #294653;border-radius:20px;background:#07131eee}.pill{left:14px}.hud{right:14px}.flow{position:absolute;left:16px;bottom:16px;z-index:3;display:none;padding:8px 11px;border:1px solid #2a705e;border-radius:8px;background:#071a16ee;color:#b4f5e4;font:11px monospace}.side{overflow:auto;padding:14px;background:#07141c;border-left:1px solid #294653}.card{padding:11px;margin:9px 0;border:1px solid #294653;border-radius:10px;background:#0b1821}.k{font-size:10px;color:#91a8b5;letter-spacing:.08em}.big{font-size:24px;font-weight:900;color:#39e6b8}.row{display:flex;justify-content:space-between;margin:7px 0}.state{display:grid;grid-template-columns:1fr 1fr;gap:6px}.s{padding:8px;border:1px solid #203844;border-radius:7px}.seq div{padding:7px;margin:3px 0;border:1px solid #1d3440;border-radius:7px;color:#708895}.seq .done{background:#0c211b;color:#b0f4e2;border-color:#2a705e}.btn{width:100%;padding:10px;margin-top:6px;border:1px solid #294653;border-radius:8px;background:#122532;color:white;font-weight:800;cursor:pointer}.warn{color:#ffb34c}.status{padding:8px;border:1px solid #294653;border-radius:7px;margin-top:8px}.log{height:90px;overflow:auto;background:#051017;padding:6px;font:9px monospace}.hint{color:#8da3ad;font-size:10px;line-height:1.5}</style></head><body><div id="app"><section id="view"><div class="pill"><b>VANNIKAWACHH</b> · REAL DJI F450 HARDWARE</div><div id="hud" class="hud">IDLE · 0 RPM · 0.0 m AGL</div><canvas id="c"></canvas><div id="flow" class="flow"></div></section><aside class="side">
<div class="card"><div class="k">AIRCRAFT</div><div id="st" class="big">IDLE</div><div class="row"><span>Mission</span><b id="mi">—</b></div><div class="row"><span>Speed</span><b id="sp">0.0 m/s</b></div><div class="row"><span>Altitude AGL</span><b id="al">0.0 m</b></div><div class="row"><span>Motor RPM</span><b id="rpm">0</b></div></div>
<div class="card"><div class="k">SYSTEM POWER-UP</div><div class="state"><div class="s">BATTERY/PDB<br><b id="bat">STANDBY</b></div><div class="s">PIXHAWK<br><b id="px">OFF</b></div><div class="s">GPS/COMPASS<br><b id="gps">NO FIX</b></div><div class="s">TELEMETRY<br><b id="tm">OFFLINE</b></div><div class="s">ESC ×4<br><b id="esc">OFF</b></div><div class="s">PAYLOAD SERVO<br><b id="sv">CLOSED</b></div></div></div>
<div class="card"><div class="k">MISSION SEQUENCE</div><div class="seq"><div id="q1">1. Distress trigger</div><div id="q2">2. Power / boot</div><div id="q3">3. GPS lock</div><div id="q4">4. Arm / rotor spool</div><div id="q5">5. Vertical takeoff</div><div id="q6">6. Enroute / hover</div><div id="q7">7. Open payload</div><div id="q8">8. Release health kit</div><div id="q9">9. RTL / land</div></div></div>
<div class="card"><div class="k">HARDWARE REFERENCE</div><div class="row"><span>Frame</span><b>DJI F450 Flame Wheel</b></div><div class="row"><span>Motors</span><b>DJI 2312E 960KV ×4</b></div><div class="row"><span>Flight controller</span><b>Pixhawk / Cube</b></div><div class="row"><span>Power</span><b>LiPo → PDB → ESC ×4</b></div><div class="row"><span>Control</span><b>Pixhawk → ESC</b></div><div class="row"><span>Signal</span><b>ESP32 → Hub → FC</b></div></div>
<button id="td" class="btn">TEST DISTRESS</button><button id="cam" class="btn">RESET CAMERA</button><button id="ex" class="btn warn">EXPLODE VIEW</button><button id="as" class="btn">ASSEMBLE VIEW</button><div id="msg" class="status">Loading F450 assets…</div><div class="hint">Drag = rotate the F450 itself · wheel = zoom · Shift-drag = pan · assembled by default</div><div id="log" class="log"></div>
</aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as T from 'three';import{STLLoader}from'three/addons/loaders/STLLoader.js';import{ColladaLoader}from'three/addons/loaders/ColladaLoader.js';
const $=id=>document.getElementById(id),U='/drone-assets/';const scene=new T.Scene();scene.background=new T.Color(0x061017);const cam=new T.PerspectiveCamera(38,1,.001,100);const ren=new T.WebGLRenderer({canvas:$('c'),antialias:true});ren.setPixelRatio(Math.min(devicePixelRatio,2));scene.add(new T.HemisphereLight(0xe7f2ff,0x12171b,2));const sun=new T.DirectionalLight(0xffffff,3);sun.position.set(3,5,4);scene.add(sun);scene.add(new T.GridHelper(8,16,0x173640,0x0c242d));const drone=new T.Group();scene.add(drone);const parts=[],props=[];let done=0,failed=0,rpm=0,exploded=false,currentAltitude=0,targetAltitude=0,currentState='IDLE',lastState='IDLE';const mats={f:new T.MeshStandardMaterial({color:0x34393d,metalness:.65,roughness:.3}),r:new T.MeshStandardMaterial({color:0xb33740,metalness:.35,roughness:.3}),w:new T.MeshStandardMaterial({color:0xe4e8eb,metalness:.15,roughness:.35}),b:new T.MeshStandardMaterial({color:0x15191c,metalness:.65,roughness:.28})};
function log(x){$('log').innerHTML+=new Date().toLocaleTimeString()+' · '+x+'<br>';$('log').scrollTop=99999}function resize(){const a=$('view').getBoundingClientRect();cam.aspect=a.width/a.height;cam.updateProjectionMatrix();ren.setSize(a.width,a.height,false)}function normGeom(m,target){m.geometry.computeBoundingBox();const s=m.geometry.boundingBox.getSize(new T.Vector3()),max=Math.max(s.x,s.y,s.z);if(max>0)m.scale.setScalar(target/max)}function normScene(root,target){const b=new T.Box3().setFromObject(root),s=b.getSize(new T.Vector3()),max=Math.max(s.x,s.y,s.z);if(max>0)root.scale.setScalar(target/max)}function add(o,pos,ex){o.position.set(...pos);o.userData.base=o.position.clone();o.userData.ex=new T.Vector3(...ex);drone.add(o);parts.push(o)}
function stl(name,mat,pos,ex,target){new STLLoader().load(U+name,g=>{const o=new T.Mesh(g,mat);normGeom(o,target);add(o,pos,ex);done++;check()},undefined,()=>{failed++;log('mesh failed '+name);check()})}function dae(name,pos,ex,dir){new ColladaLoader().load(U+name,x=>{x.scene.traverse(n=>{if(n.isMesh)n.material=mats.w});normScene(x.scene,.22);x.scene.position.set(...pos);x.scene.userData.base=x.scene.position.clone();x.scene.userData.ex=new T.Vector3(...ex);x.scene.userData.dir=dir;drone.add(x.scene);parts.push(x.scene);props.push(x.scene);done++;check()},undefined,()=>{failed++;log('prop failed '+name);check()})}
function check(){if(done+failed!==15)return;resetCamera();setExploded(false);$('msg').textContent=failed?`F450 loaded: ${done}/15 · ${failed} failed`:'F450 loaded: 15/15 assets';log('MODEL LOAD COMPLETE '+done+'/15')}
function resetCamera(){const b=new T.Box3().setFromObject(drone),c=b.getCenter(new T.Vector3()),s=b.getSize(new T.Vector3()),m=Math.max(s.x,s.y,s.z)||1;drone.position.x-=c.x;drone.position.z-=c.z;cam.position.set(m*1.7,m*1.15,m*1.7);cam.lookAt(0,0,0)}
function setExploded(v){exploded=v;parts.forEach(p=>p.position.copy(v?p.userData.ex:p.userData.base));$('ex').textContent=v?'ASSEMBLE VIEW':'EXPLODE VIEW'}
// assembled SDF-inspired positions
stl('base_link.stl',mats.f,[0,0,0],[0,.55,0],.88);stl('leg_link.stl',mats.w,[0,0,.132],[0,-.28,-.5],.30);stl('battery_link.stl',mats.b,[-.025,-.0002,.09],[-.48,-.18,0],.26);
[[.098,.098,.171],[.098,-.098,.171],[-.098,-.098,.171],[-.098,.098,.171]].forEach((p,i)=>stl(i<2?'front_arm_link.stl':'back_arm_link.STL',i%2?mats.w:mats.r,p,[p[0]*3.8,.30,p[1]*3.8],.43));[[.15988,-.15988,.206],[-.15988,.15988,.206],[.15988,.15988,.206],[-.15988,-.15988,.206]].forEach((p,i)=>{stl('motor_link.STL',mats.b,[p[0],p[1],.173],[p[0]*3.2,.38,p[1]*3.2],.075);dae(i%2?'iris_prop_cw.dae':'iris_prop_ccw_centered.dae',p,[p[0]*3.4,.43,p[1]*3.4],i%2?-1:1)});
// The aircraft itself rotates. The grid/world never rotates.
let dragging=false,shiftPan=false,lastX=0,lastY=0;const canvas=$('c');canvas.addEventListener('pointerdown',e=>{dragging=true;shiftPan=e.shiftKey;lastX=e.clientX;lastY=e.clientY;canvas.classList.add('drag');canvas.setPointerCapture(e.pointerId)});canvas.addEventListener('pointermove',e=>{if(!dragging)return;const dx=e.clientX-lastX,dy=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;if(shiftPan){cam.position.x-=dx*.0015;cam.position.y+=dy*.0015;cam.lookAt(0,0,0)}else{drone.rotation.y+=dx*.012;drone.rotation.x+=dy*.009}});canvas.addEventListener('pointerup',e=>{dragging=false;canvas.classList.remove('drag');try{canvas.releasePointerCapture(e.pointerId)}catch(_){}});canvas.addEventListener('pointerleave',()=>{dragging=false;canvas.classList.remove('drag')});canvas.addEventListener('wheel',e=>{e.preventDefault();cam.position.multiplyScalar(Math.exp(e.deltaY*.0008));cam.lookAt(0,0,0)},{passive:false});
function apply(x){const q=x.state||'IDLE';currentState=q;rpm=+x.motor_rpm||0;targetAltitude=Math.max(0,+x.altitude_m||0);$('st').textContent=q;$('mi').textContent=x.mission_id||'—';$('sp').textContent=(+x.speed_ms||0).toFixed(1)+' m/s';$('al').textContent=targetAltitude.toFixed(1)+' m';$('rpm').textContent=Math.round(rpm);const on=q!=='IDLE'&&q!=='COMPLETED',fly=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(q);$('bat').textContent=on?'ON':'STANDBY';$('px').textContent=on?'BOOTED':'OFF';$('gps').textContent=fly||q==='ARMING'?'LOCKED':'NO FIX';$('tm').textContent=on?'ONLINE':'OFFLINE';$('esc').textContent=fly?'ACTIVE':q==='ARMING'?'SPOOLING':'OFF';$('sv').textContent=q==='DELIVERING'?'OPEN':'CLOSED';const m={q1:on,q2:on,q3:fly||q==='ARMING',q4:fly,q5:['ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'].includes(q),q6:['HOVERING','DELIVERING','RTL','LANDING','COMPLETED'].includes(q),q7:['DELIVERING','RTL','LANDING','COMPLETED'].includes(q),q8:['RTL','LANDING','COMPLETED'].includes(q),q9:['RTL','LANDING','COMPLETED'].includes(q)};Object.entries(m).forEach(([id,v])=>$(id).className=v?'done':'');if(q!==lastState){log('STATE → '+q);lastState=q}}
async function poll(){try{apply(await(await fetch('/drone_state?ts='+Date.now(),{cache:'no-store'})).json())}catch(_){log('telemetry unavailable')}setTimeout(poll,700)}
$('td').onclick=async()=>{try{const r=await fetch('/node-alert?node=WEB-F450-V6&lat=21.128&lon=79.047&event=1&conf=.99&pir=1&light=30');$('msg').textContent=r.ok?'DISTRESS ACCEPTED':'TRIGGER FAILED'}catch(_){$('msg').textContent='TRIGGER FAILED'}};$('cam').onclick=resetCamera;$('ex').onclick=()=>setExploded(!exploded);$('as').onclick=()=>setExploded(false);
function loop(){requestAnimationFrame(loop);currentAltitude+=(targetAltitude-currentAltitude)*.05;drone.position.y=Math.min(currentAltitude*.035,1.8);const spin=rpm*Math.PI*2/60/60;props.forEach(p=>p.rotation.z+=spin*(p.userData.dir||1));$('hud').textContent=`${currentState} · ${Math.round(rpm)} RPM · ${currentAltitude.toFixed(1)} m AGL`;const active=currentState!=='IDLE'&&currentState!=='COMPLETED';$('flow').style.display=active?'block':'none';$('flow').textContent=active?`SIGNAL FLOW  ESP32 → HUB → PIXHAWK → ESC ×4 → MOTORS  ·  ${currentState}`:'';ren.render(scene,cam)}resize();addEventListener('resize',resize);poll();loop();
</script></body></html>'''
