from fastapi.responses import HTMLResponse, Response
from urllib.request import Request, urlopen
from urllib.parse import quote
import json, base64

ASSET_DIR = "custom_f450/meshes/"
MIMES = {
    "base_link.stl":"model/stl", "front_arm_link.stl":"model/stl", "back_arm_link.STL":"model/stl",
    "motor_link.STL":"model/stl", "leg_link.stl":"model/stl", "battery_link.stl":"model/stl",
    "iris_prop_cw.dae":"model/collada+xml", "iris_prop_ccw_centered.dae":"model/collada+xml",
}
CACHE = {}

def get_asset(name):
    if name not in MIMES:
        return None
    if name in CACHE:
        return CACHE[name]
    urls = [
        "https://cdn.jsdelivr.net/gh/beomsu7/px4-quadrotor-HW-parts@main/" + ASSET_DIR + quote(name),
        "https://raw.githubusercontent.com/beomsu7/px4-quadrotor-HW-parts/main/" + ASSET_DIR + quote(name),
    ]
    last = None
    for url in urls:
        try:
            req = Request(url, headers={"User-Agent":"VanniKawachh/3.0","Accept":"*/*"})
            with urlopen(req, timeout=20) as r:
                data = r.read()
                if data:
                    CACHE[name] = data
                    return data
        except Exception as exc:
            last = exc
    try:
        api = "https://api.github.com/repos/beomsu7/px4-quadrotor-HW-parts/contents/" + ASSET_DIR + quote(name)
        req = Request(api, headers={"User-Agent":"VanniKawachh/3.0","Accept":"application/vnd.github+json"})
        with urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8"))
        data = base64.b64decode(payload["content"])
        CACHE[name] = data
        return data
    except Exception as exc:
        last = exc
    raise RuntimeError(str(last))

def attach(app):
    @app.get('/drone-assets/{name}', include_in_schema=False)
    def asset(name: str):
        try:
            data = get_asset(name)
            if data is None:
                return Response(status_code=404)
            return Response(data, media_type=MIMES[name], headers={"Cache-Control":"public,max-age=3600"})
        except Exception as exc:
            return Response(str(exc), status_code=502, media_type='text/plain')

    @app.get('/drone-hardware', response_class=HTMLResponse)
    def page():
        return HTML

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VanniKawachh · F450 Hardware</title>
<style>html,body{margin:0;height:100%;overflow:hidden;background:#061017;color:#eef5f7;font:12px Segoe UI,Arial}#app{display:grid;grid-template-columns:minmax(0,1fr) 360px;height:100%}#v{position:relative;min-width:0}canvas{width:100%;height:100%;display:block}aside{overflow:auto;padding:14px;background:#07141c;border-left:1px solid #294653}.pill{position:absolute;z-index:3;left:14px;top:14px;padding:9px 12px;border:1px solid #294653;border-radius:20px;background:#07131eee}.card{padding:11px;margin:9px 0;border:1px solid #294653;border-radius:10px;background:#0b1821}.k{font-size:10px;color:#91a8b5;letter-spacing:.08em}.big{font-size:24px;font-weight:900;color:#39e6b8}.row{display:flex;justify-content:space-between;margin:7px 0}.state{display:grid;grid-template-columns:1fr 1fr;gap:6px}.s{padding:8px;border:1px solid #203844;border-radius:7px}.seq div{padding:7px;margin:3px 0;border:1px solid #1d3440;border-radius:7px;color:#708895}.seq .done{background:#0c211b;color:#b0f4e2;border-color:#2a705e}.btn{width:100%;padding:10px;margin-top:6px;border:1px solid #294653;border-radius:8px;background:#122532;color:white;font-weight:800;cursor:pointer}.warn{color:#ffb34c}.status{padding:8px;border:1px solid #294653;border-radius:7px;margin-top:8px}.hint{color:#8da3ad;font-size:10px;line-height:1.5}.log{height:100px;overflow:auto;background:#051017;padding:6px;font:9px monospace}</style></head><body>
<div id="app"><section id="v"><div class="pill"><b>VANNIKAWACHH</b> · REAL F450 HARDWARE v3</div><canvas id="c"></canvas></section><aside>
<div class="card"><div class="k">AIRCRAFT</div><div id="st" class="big">IDLE</div><div class="row"><span>Mission</span><b id="mi">—</b></div><div class="row"><span>Speed</span><b id="sp">0.0 m/s</b></div><div class="row"><span>Altitude AGL</span><b id="al">0.0 m</b></div><div class="row"><span>Motor RPM</span><b id="rpm">0</b></div></div>
<div class="card"><div class="k">SYSTEM POWER-UP</div><div class="state"><div class="s">BATTERY/PDB<br><b id="bat">STANDBY</b></div><div class="s">PIXHAWK<br><b id="px">OFF</b></div><div class="s">GPS/COMPASS<br><b id="gps">NO FIX</b></div><div class="s">TELEMETRY<br><b id="tm">OFFLINE</b></div><div class="s">ESC ×4<br><b id="esc">OFF</b></div><div class="s">PAYLOAD SERVO<br><b id="sv">CLOSED</b></div></div></div>
<div class="card"><div class="k">MISSION SEQUENCE</div><div class="seq"><div id="q1">1. Distress trigger</div><div id="q2">2. Power / boot</div><div id="q3">3. GPS lock</div><div id="q4">4. Arm / rotor spool</div><div id="q5">5. Takeoff</div><div id="q6">6. Enroute / hover</div><div id="q7">7. Open payload</div><div id="q8">8. Release health kit</div><div id="q9">9. RTL / land</div></div></div>
<div class="card"><div class="k">HARDWARE REFERENCE</div><div class="row"><span>Frame</span><b>DJI F450</b></div><div class="row"><span>Motors</span><b>2312E 960KV ×4</b></div><div class="row"><span>Flight controller</span><b>Pixhawk / Cube</b></div><div class="row"><span>Power</span><b>LiPo → PDB → ESC ×4</b></div><div class="row"><span>Control</span><b>Pixhawk → ESC</b></div><div class="row"><span>Signal</span><b>ESP32 → Hub → FC</b></div></div>
<button id="td" class="btn">TEST DISTRESS</button><button id="cam" class="btn">RESET CAMERA</button><button id="lb" class="btn">SHOW LABELS</button><button id="ex" class="btn warn">EXPLODE VIEW</button><button id="as" class="btn">ASSEMBLE VIEW</button><div id="msg" class="status">F450 v3 · loading…</div><div class="hint">Drag = rotate · wheel = zoom · right-drag = pan. Starts assembled.</div><div id="log" class="log"></div>
</aside></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.185.0/examples/jsm/"}}</script>
<script type="module">
import * as T from 'three';import{OrbitControls}from'three/addons/controls/OrbitControls.js';import{STLLoader}from'three/addons/loaders/STLLoader.js';import{ColladaLoader}from'three/addons/loaders/ColladaLoader.js';
const $=id=>document.getElementById(id),U='/drone-assets/';const sc=new T.Scene();sc.background=new T.Color(0x061017);const cam=new T.PerspectiveCamera(38,1,.001,100);const ren=new T.WebGLRenderer({canvas:$('c'),antialias:true});ren.setPixelRatio(Math.min(devicePixelRatio,2));const ctl=new OrbitControls(cam,ren.domElement);ctl.enableDamping=true;ctl.enablePan=true;ctl.rotateSpeed=.7;ctl.zoomSpeed=.9;sc.add(new T.HemisphereLight(0xe7f2ff,0x12171b,2));const sun=new T.DirectionalLight(0xffffff,3);sun.position.set(3,5,4);sc.add(sun);sc.add(new T.GridHelper(8,16,0x173640,0x0c242d));const d=new T.Group();sc.add(d);const parts=[],props=[];let done=0,failed=0,rpm=0,exploded=false,last='IDLE';const mats={f:new T.MeshStandardMaterial({color:0x34393d,metalness:.65,roughness:.3}),r:new T.MeshStandardMaterial({color:0xb33740,metalness:.35,roughness:.3}),w:new T.MeshStandardMaterial({color:0xe4e8eb,metalness:.15,roughness:.35}),b:new T.MeshStandardMaterial({color:0x15191c,metalness:.65,roughness:.28})};
function log(x){$('log').innerHTML+=new Date().toLocaleTimeString()+' · '+x+'<br>';$('log').scrollTop=99999}
function normGeom(m,target){m.geometry.computeBoundingBox();const s=m.geometry.boundingBox.getSize(new T.Vector3()),max=Math.max(s.x,s.y,s.z);if(max>0)m.scale.setScalar(target/max)}
function normScene(root,target){const box=new T.Box3().setFromObject(root),s=box.getSize(new T.Vector3()),max=Math.max(s.x,s.y,s.z);if(max>0)root.scale.setScalar(target/max)}
function add(o,pos,ex){o.position.set(...pos);o.userData.base=o.position.clone();o.userData.ex=new T.Vector3(...ex);d.add(o);parts.push(o)}
function stl(name,mat,pos,ex,target){new STLLoader().load(U+name,g=>{const o=new T.Mesh(g,mat);normGeom(o,target);add(o,pos,ex);done++;check()},undefined,()=>{failed++;log('mesh failed '+name);check()})}
function dae(name,pos,ex,dir){new ColladaLoader().load(U+name,x=>{x.scene.traverse(o=>{if(o.isMesh)o.material=mats.w});normScene(x.scene,.22);x.scene.position.set(...pos);x.scene.userData.base=x.scene.position.clone();x.scene.userData.ex=new T.Vector3(...ex);x.scene.userData.dir=dir;d.add(x.scene);parts.push(x.scene);props.push(x.scene);done++;check()},undefined,()=>{failed++;log('prop failed '+name);check()})}
function check(){if(done+failed!==15)return;resetCamera();setExploded(false);$('msg').textContent=failed?`F450 v3 · ${done}/15 loaded · ${failed} failed`:'F450 v3 · 15/15 assets loaded';log(`LOAD COMPLETE ${done}/15`) }
function resetCamera(){const b=new T.Box3().setFromObject(d),c=b.getCenter(new T.Vector3()),s=b.getSize(new T.Vector3()),m=Math.max(s.x,s.y,s.z)||1;d.position.sub(c);cam.position.set(m*1.7,m*1.15,m*1.7);ctl.target.set(0,0,0);ctl.minDistance=m*.55;ctl.maxDistance=m*6;ctl.update()}
function setExploded(v){exploded=v;for(const p of parts)p.position.copy(v?p.userData.ex:p.userData.base);$('ex').textContent=v?'ASSEMBLE VIEW':'EXPLODE VIEW'}
stl('base_link.stl',mats.f,[0,0,0],[0,.55,0],.88);stl('leg_link.stl',mats.w,[0,0,.132],[0,-.28,-.50],.30);stl('battery_link.stl',mats.b,[-.025,-.0002,.09],[-.48,-.18,0],.26);
[[.098,.098,.171],[.098,-.098,.171],[-.098,-.098,.171],[-.098,.098,.171]].forEach((p,i)=>stl(i<2?'front_arm_link.stl':'back_arm_link.STL',i%2?mats.w:mats.r,p,[p[0]*3.8,.30,p[1]*3.8],.43));
[[.15988,-.15988,.206],[-.15988,.15988,.206],[.15988,.15988,.206],[-.15988,-.15988,.206]].forEach((p,i)=>{stl('motor_link.STL',mats.b,[p[0],p[1],.173],[p[0]*3.2,.38,p[1]*3.2],.075);dae(i%2?'iris_prop_cw.dae':'iris_prop_ccw_centered.dae',p,[p[0]*3.4,.43,p[1]*3.4],i%2?-1:1)});
function apply(x){const q=x.state||'IDLE';rpm=+x.motor_rpm||0;$('st').textContent=q;$('mi').textContent=x.mission_id||'—';$('sp').textContent=(+x.speed_ms||0).toFixed(1)+' m/s';$('al').textContent=(+x.altitude_m||0).toFixed(1)+' m';$('rpm').textContent=Math.round(rpm);const on=q!=='IDLE',fly=['TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'].includes(q);$('bat').textContent=on?'ON':'STANDBY';$('px').textContent=on?'BOOTED':'OFF';$('gps').textContent=fly||q==='ARMING'?'LOCKED':'NO FIX';$('tm').textContent=on?'ONLINE':'OFFLINE';$('esc').textContent=fly?'ACTIVE':q==='ARMING'?'SPOOLING':'OFF';$('sv').textContent=q==='DELIVERING'?'OPEN':'CLOSED';[['q1',on],['q2',on],['q3',fly||q==='ARMING'],['q4',fly],['q5',['ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'].includes(q)],['q6',['HOVERING','DELIVERING','RTL','LANDING','COMPLETED'].includes(q)],['q7',['DELIVERING','RTL','LANDING','COMPLETED'].includes(q)],['q8',['RTL','LANDING','COMPLETED'].includes(q)],['q9',['RTL','LANDING','COMPLETED'].includes(q)]].forEach(([id,v])=>$(id).className=v?'done':'');if(q!==last){log('STATE → '+q);last=q}}
async function poll(){try{apply(await(await fetch('/drone_state?ts='+Date.now(),{cache:'no-store'})).json())}catch(e){log('telemetry unavailable')}setTimeout(poll,700)}
$('td').onclick=async()=>{try{const r=await fetch('/node-alert?node=WEB-F450-V3&lat=21.128&lon=79.047&event=1&conf=.99&pir=1&light=30');$('msg').textContent=r.ok?'DISTRESS ACCEPTED':'TRIGGER FAILED'}catch(e){$('msg').textContent='TRIGGER FAILED'}};$('cam').onclick=resetCamera;$('ex').onclick=()=>setExploded(!exploded);$('as').onclick=()=>setExploded(false);let labels=false;$('lb').onclick=()=>{labels=!labels;$('lb').textContent=labels?'HIDE LABELS':'SHOW LABELS'};
function resize(){const a=$('v').getBoundingClientRect();cam.aspect=a.width/a.height;cam.updateProjectionMatrix();ren.setSize(a.width,a.height,false)}addEventListener('resize',resize);resize();poll();let prev=performance.now();function loop(t){requestAnimationFrame(loop);const dt=(t-prev)/1000;prev=t;const w=rpm*Math.PI*2/60*dt;for(const p of props)p.rotation.z+=w*(p.userData.dir||1);ctl.update();ren.render(sc,cam)}requestAnimationFrame(loop);
</script></body></html>'''
