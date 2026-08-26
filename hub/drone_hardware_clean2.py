from fastapi.responses import HTMLResponse, Response
from urllib.request import Request, urlopen

ASSET_BASE = "https://raw.githubusercontent.com/beomsu7/px4-quadrotor-HW-parts/main/custom_f450/meshes/"
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
_CACHE = {}


def _asset(name):
    if name not in ASSETS:
        return Response(status_code=404)
    if name not in _CACHE:
        req = Request(ASSET_BASE + name, headers={"User-Agent": "VanniKawachh-F450/1.0"})
        with urlopen(req, timeout=20) as r:
            _CACHE[name] = r.read()
    return Response(content=_CACHE[name], media_type=ASSETS[name], headers={"Cache-Control": "public, max-age=3600"})


def attach(app):
    @app.get('/drone-assets/{name}', include_in_schema=False)
    def asset(name: str):
        return _asset(name)

    @app.get('/drone-hardware', response_class=HTMLResponse)
    def page():
        return HTML


HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VanniKawachh — F450 Hardware</title><style>
html,body{margin:0;height:100%;overflow:hidden;background:#061017;color:#eef5f7;font:12px Arial,sans-serif}#app{display:grid;grid-template-columns:1fr 360px;height:100%}#v{position:relative;min-width:0}canvas{width:100%;height:100%;display:block}aside{overflow:auto;padding:14px;background:#07141c;border-left:1px solid #294653}.pill{position:absolute;z-index:3;top:14px;left:14px;padding:9px 12px;border:1px solid #294653;border-radius:20px;background:#07131eee;letter-spacing:.02em}.card{padding:11px;margin:9px 0;border:1px solid #294653;border-radius:10px;background:#0b1821}.k{color:#91a8b5;font-size:10px;letter-spacing:.08em}.big{font-size:24px;font-weight:900;color:#39e6b8}.row{display:flex;justify-content:space-between;margin:7px 0}.btn{width:100%;padding:10px;margin-top:6px;border:1px solid #294653;border-radius:8px;background:#122532;color:#fff;font-weight:800;cursor:pointer}.btn:hover{background:#173443}.warn{color:#ffb34c}.state{display:grid;grid-template-columns:1fr 1fr;gap:6px}.s{padding:8px;border:1px solid #203844;border-radius:7px}.seq div{padding:7px;margin:3px 0;border:1px solid #1d3440;border-radius:7px;color:#708895}.seq .done{background:#0c211b;color:#b0f4e2;border-color:#2a705e}.status{padding:8px;border:1px solid #294653;border-radius:7px;margin-top:8px}.log{height:90px;overflow:auto;background:#051017;padding:6px;font:9px monospace}.hint{color:#8da3ad;font-size:10px;line-height:1.4}.ok{color:#39e6b8}</style></head><body><div id="app"><section id="v"><div class="pill"><b>VANNIKAWACHH</b> · REAL F450 HARDWARE</div><canvas id="c"></canvas></section><aside>
<div class="card"><div class="k">AIRCRAFT</div><div id="st" class="big">IDLE</div><div class="row"><span>Mission</span><b id="mi">—</b></div><div class="row"><span>Speed</span><b id="sp">0.0 m/s</b></div><div class="row"><span>Altitude AGL</span><b id="al">0.0 m</b></div><div class="row"><span>Motor RPM</span><b id="rp">0</b></div></div>
<div class="card"><div class="k">SYSTEM POWER-UP</div><div class="state"><div class="s">BATTERY/PDB<br><b id="bat">STANDBY</b></div><div class="s">PIXHAWK<br><b id="px">OFF</b></div><div class="s">GPS/COMPASS<br><b id="gps">NO FIX</b></div><div class="s">TELEMETRY<br><b id="tm">OFFLINE</b></div><div class="s">ESC ×4<br><b id="esc">OFF</b></div><div class="s">PAYLOAD SERVO<br><b id="sv">CLOSED</b></div></div></div>
<div class="card"><div class="k">MISSION SEQUENCE</div><div class="seq"><div id="q1">1. Distress trigger</div><div id="q2">2. Power / boot</div><div id="q3">3. GPS lock</div><div id="q4">4. Arm / rotor spool</div><div id="q5">5. Takeoff</div><div id="q6">6. Enroute / hover</div><div id="q7">7. Open payload</div><div id="q8">8. Release health kit</div><div id="q9">9. RTL / land</div></div></div>
<div class="card"><div class="k">HARDWARE REFERENCE</div><div class="row"><span>Frame</span><b>DJI F450</b></div><div class="row"><span>Motors</span><b>2312E 960KV ×4</b></div><div class="row"><span>Flight controller</span><b>Pixhawk / Cube</b></div><div class="row"><span>Power</span><b>LiPo → PDB → ESC ×4</b></div><div class="row"><span>Control</span><b>Pixhawk → ESC</b></div><div class="row"><span>Signal</span><b>ESP32 → Hub → FC</b></div></div>
<button id="td" class="btn">TEST DISTRESS</button><button id="cam" class="btn">RESET CAMERA</button><button id="lb" class="btn">SHOW LABELS</button><button id="ex" class="btn warn">EXPLODE VIEW</button><button id="as" class="btn">ASSEMBLE VIEW</button><div class="status" id="msg">Loading F450 model…</div><div class="hint">Drag to orbit · wheel to zoom · right-drag to pan</div><div class="log" id="log"></div></aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as T from 'three';import{OrbitControls}from'three/addons/controls/OrbitControls.js';import{STLLoader}from'three/addons/loaders/STLLoader.js';import{ColladaLoader}from'three/addons/loaders/ColladaLoader.js';
const $=x=>document.getElementById(x);const U='/drone-assets/';
const scene=new T.Scene();scene.background=new T.Color(0x061017);const cam=new T.PerspectiveCamera(38,1,.001,100);const renderer=new T.WebGLRenderer({canvas:$('c'),antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
const controls=new OrbitControls(cam,renderer.domElement);controls.enableDamping=true;controls.enablePan=true;controls.rotateSpeed=.65;controls.zoomSpeed=.9;
scene.add(new T.HemisphereLight(0xe7f2ff,0x12171b,2.0));const dl=new T.DirectionalLight(0xffffff,3.0);dl.position.set(3,5,4);scene.add(dl);const grid=new T.GridHelper(8,16,0x173640,0x0c242d);scene.add(grid);
const drone=new T.Group();scene.add(drone);const loaded=[];const props=[];let exploded=false,rpm=0,last='IDLE';let loadTotal=15,done=0,failed=0;
const mats={frame:new T.MeshStandardMaterial({color:0x3d4246,metalness:.65,roughness:.3}),red:new T.MeshStandardMaterial({color:0xb33a42,metalness:.35,roughness:.3}),white:new T.MeshStandardMaterial({color:0xe4e8eb,metalness:.15,roughness:.35}),black:new T.MeshStandardMaterial({color:0x15191c,metalness:.65,roughness:.28})};
function log(x){$('log').innerHTML+='<div>'+x+'</div>';$('log').scrollTop=99999}function fit(mesh,target){mesh.geometry.computeBoundingBox();const b=mesh.geometry.boundingBox;const s=b.getSize(new T.Vector3());const m=Math.max(s.x,s.y,s.z);if(m>0)mesh.scale.setScalar(target/m)}
function finish(){const box=new T.Box3().setFromObject(drone);const c=box.getCenter(new T.Vector3());drone.position.sub(c);resetCamera();$('msg').textContent=failed?`F450 loaded: ${done}/15 · ${failed} asset failures`:`F450 loaded: 15/15 assets`}
function addPart(o,pos,explode,group=drone){o.position.set(...pos);o.userData.base=o.position.clone();o.userData.explode=new T.Vector3(...explode);group.add(o);loaded.push(o)}
function stl(name,mat,pos,explode,target,tag){new STLLoader().load(U+name,g=>{const o=new T.Mesh(g,mat);fit(o,target);addPart(o,pos,explode);done++;if(done+failed===loadTotal)finish()},undefined,e=>{failed++;log(tag||`mesh failed ${name}`);if(done+failed===loadTotal)finish()})}
function dae(name,pos,explode,dir){new ColladaLoader().load(U+name,x=>{x.scene.traverse(o=>{if(o.isMesh){o.material=mats.white;o.castShadow=o.receiveShadow=true}});fit(x.scene.children[0]||x.scene,.26);x.scene.position.set(...pos);x.scene.userData.base=x.scene.position.clone();x.scene.userData.explode=new T.Vector3(...explode);x.scene.userData.dir=dir;drone.add(x.scene);loaded.push(x.scene);props.push(x.scene);done++;if(done+failed===loadTotal)finish()},undefined,e=>{failed++;log(`prop failed ${name}`);if(done+failed===loadTotal)finish()})}
// SDF-inspired assembled positions. Geometry is normalized because STL/DAE files do not carry reliable units.
stl('base_link.stl',mats.frame,[0,0,0],[0,.45,0],.88);
stl('leg_link.stl',mats.white,[0,0,.132],[0,-.2,-.45],.30);
stl('battery_link.stl',mats.black,[-.025,-.0002,.09],[-.38,-.2,0],.26);
[[.098,.098,.171],[.098,-.098,.171],[-.098,-.098,.171],[-.098,.098,.171]].forEach((p,i)=>stl(i<2?'front_arm_link.stl':'back_arm_link.STL',i%2?mats.white:mats.red,p,[p[0]*4,.22,p[1]*4],.43));
const motors=[[.15988,-.15988,.206],[-.15988,.15988,.206],[.15988,.15988,.206],[-.15988,-.15988,.206]];
motors.forEach((p,i)=>{stl('motor_link.STL',mats.black,[p[0],p[1],.173],[p[0]*2.5,.35,p[1]*2.5],.065,`motor ${i+1} failed`);dae(i%2?'iris_prop_cw.dae':'iris_prop_ccw_centered.dae',p,[p[0]*2.7,.45,p[1]*2.7],i%2?-1:1)});
function resetCamera(){const box=new T.Box3().setFromObject(drone);const size=box.getSize(new T.Vector3());const m=Math.max(size.x,size.y,size.z)||1;cam.position.set(m*1.65,m*1.15,m*1.65);controls.target.set(0,0,0);controls.minDistance=m*.75;controls.maxDistance=m*6;controls.update()}
function setExploded(v){exploded=v;loaded.forEach(o=>{o.position.copy(v?o.userData.explode:o.userData.base)});$('ex').textContent=v?'ASSEMBLE VIEW':'EXPLODE VIEW'}
function state(x){const q=x.state||'IDLE';rpm=+x.motor_rpm||0;$('st').textContent=q;$('mi').textContent=x.mission_id||'—';$('sp').textContent=(+x.speed_ms||0).toFixed(1)+' m/s';$('al').textContent=(+x.altitude_m||0).toFixed(1)+' m';$('rp').textContent=Math.round(rpm);const on=q!=='IDLE';const fly=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(q);$('bat').textContent=on?'ON':'STANDBY';$('px').textContent=on?'BOOTED':'OFF';$('gps').textContent=fly||q==='ARMING'?'LOCKED':'NO FIX';$('tm').textContent=on?'ONLINE':'OFFLINE';$('esc').textContent=fly?'ACTIVE':q==='ARMING'?'SPOOLING':'OFF';$('sv').textContent=q==='DELIVERING'?'OPEN':'CLOSED';[['q1',on],['q2',on],['q3',fly||q==='ARMING'],['q4',fly],['q5',['ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'].includes(q)],['q6',['HOVERING','DELIVERING','RTL','LANDING','COMPLETED'].includes(q)],['q7',['DELIVERING','RTL','LANDING','COMPLETED'].includes(q)],['q8',['RTL','LANDING','COMPLETED'].includes(q)],['q9',['RTL','LANDING','COMPLETED'].includes(q)]].forEach(([id,v])=>$(id).className=v?'done':'');if(q!==last){log('STATE → '+q);last=q}}
async function poll(){try{state(await(await fetch('/drone_state?ts='+Date.now(),{cache:'no-store'})).json())}catch(e){$('msg').textContent='Hub telemetry unavailable';log('telemetry error')}setTimeout(poll,700)}
$('td').onclick=async()=>{try{const r=await fetch('/node-alert?node=WEB-F450&lat=21.128&lon=79.047&event=1&conf=0.99&pir=1&light=30');$('msg').textContent=r.ok?'DISTRESS ACCEPTED':'TRIGGER FAILED'}catch(e){$('msg').textContent='TRIGGER FAILED'}};$('cam').onclick=resetCamera;$('ex').onclick=()=>setExploded(!exploded);$('as').onclick=()=>setExploded(false);let labels=false;$('lb').onclick=()=>{labels=!labels;$('lb').textContent=labels?'HIDE LABELS':'SHOW LABELS'};
function resize(){const a=$('v').getBoundingClientRect();cam.aspect=a.width/a.height;cam.updateProjectionMatrix();renderer.setSize(a.width,a.height,false)}addEventListener('resize',resize);resize();poll();let prev=performance.now();function loop(t){requestAnimationFrame(loop);const dt=(t-prev)/1000;prev=t;const spin=rpm*Math.PI*2/60*dt;props.forEach(p=>p.rotation.z+=spin*(p.userData.dir||1));controls.update();renderer.render(scene,cam)}requestAnimationFrame(loop);
</script></body></html>'''
