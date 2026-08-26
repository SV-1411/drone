"""GCS-style geographic drone simulator for VanniKawachh.

This is the browser presentation/mission layer. It reads /drone_state as the
single source of truth and does not require a SIMNET session.
"""
from fastapi.responses import HTMLResponse


def attach(app):
    @app.get("/drone-flight", response_class=HTMLResponse)
    def drone_flight_page():
        return HTML


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanniKawachh | GCS Flight Simulator</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/cesium@1.132.0/Build/Cesium/Widgets/widgets.css">
<style>
:root{--bg:#050a0f;--panel:#09131bdf;--line:#294451;--text:#edf7fa;--muted:#89a2b0;--green:#31e3b3;--amber:#ffb34d;--red:#ff6675;--blue:#5cb9ff;--white:#f5fbff}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:12px Inter,Segoe UI,Arial,sans-serif}
#app{width:100vw;height:100vh;position:relative}#world{position:absolute;inset:0}.cesium-viewer,.cesium-widget,.cesium-widget canvas{width:100%;height:100%}.cesium-viewer-bottom,.cesium-viewer-animationContainer,.cesium-viewer-timelineContainer{display:none!important}
.glass{background:var(--panel);border:1px solid var(--line);box-shadow:0 12px 35px #0007;backdrop-filter:blur(10px)}
#topbar{position:absolute;z-index:20;left:14px;right:14px;top:12px;display:flex;gap:10px;justify-content:space-between;pointer-events:none}.pill{padding:8px 12px;border-radius:999px}.pill b{color:#fff}.online{color:var(--green)}
#hud{position:absolute;z-index:15;left:0;right:0;top:60px;bottom:0;pointer-events:none}.reticle{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:54px;height:54px;border:1px solid #8fe7ff88;border-radius:50%}.reticle:before,.reticle:after{content:"";position:absolute;background:#8fe7ff88}.reticle:before{width:76px;height:1px;left:-12px;top:26px}.reticle:after{height:76px;width:1px;left:26px;top:-12px}
#hudTop{position:absolute;top:12px;left:50%;transform:translateX(-50%);min-width:360px;padding:6px 12px;text-align:center}.tape{font:700 11px ui-monospace,Consolas,monospace;letter-spacing:.14em;color:#d5ecf4}.hdg{font-size:22px;font-weight:900;letter-spacing:.05em}.mini{font-size:9px;color:var(--muted)}
#hudLeft{position:absolute;left:14px;top:82px;width:220px;padding:10px}.hudRow{display:flex;justify-content:space-between;gap:8px;margin:8px 0}.hudVal{font-weight:900}.hudVal.green{color:var(--green)}.hudVal.amber{color:var(--amber)}.hudVal.blue{color:var(--blue)}
#hudBottom{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);display:flex;align-items:center;gap:18px;padding:9px 14px;border-radius:9px;pointer-events:none}.hudMetric{text-align:center;min-width:78px}.hudMetric .n{font-size:18px;font-weight:900}.hudMetric .l{font-size:9px;color:var(--muted);letter-spacing:.12em}
#side{position:absolute;z-index:30;right:12px;top:64px;width:380px;bottom:12px;overflow:auto;padding:11px;border-radius:14px}.title{font-size:19px;font-weight:900}.sub{color:var(--muted);font-size:10px;line-height:1.45;margin-top:4px}.card{padding:10px;border-radius:10px;margin-top:9px}.label{font-size:9px;font-weight:900;letter-spacing:.14em;color:var(--muted);margin-bottom:6px}.state{font-size:28px;font-weight:900}.state.green{color:var(--green)}.state.amber{color:var(--amber)}.state.red{color:var(--red)}
.row{display:flex;justify-content:space-between;gap:10px;margin:7px 0}.val{font-weight:800;text-align:right}.mission{display:grid;gap:5px}.wp{display:grid;grid-template-columns:28px 1fr auto;gap:8px;align-items:center;padding:8px;border:1px solid #1b3340;border-radius:8px;background:#071119}.wp.active{border-color:#9b702f;background:#1e180e}.wp.done{border-color:#286a58;background:#0b1e19}.num{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;border:1px solid #42606d;font-weight:900}.wp.active .num{border-color:var(--amber);color:var(--amber)}.wp.done .num{border-color:var(--green);color:var(--green)}.wpName{font-weight:900}.wpMeta{font-size:9px;color:var(--muted)}
.buttons{display:grid;grid-template-columns:1fr 1fr;gap:6px}.btn{padding:9px;border:1px solid var(--line);border-radius:8px;background:#122431;color:#fff;font-weight:900;cursor:pointer}.btn.primary{background:#0d2d25;border-color:#286b5a}.btn.warn{background:#2b2214;border-color:#735228}.btn:hover{filter:brightness(1.1)}.btn:disabled{opacity:.5;cursor:wait}
.badge{display:inline-block;padding:3px 7px;border-radius:999px;border:1px solid #315061;font-size:9px}.badge.green{color:var(--green);border-color:#286b5a}.badge.amber{color:var(--amber);border-color:#705126}.badge.blue{color:var(--blue);border-color:#355f7d}
#status{margin-top:8px;padding:8px;border-radius:8px;font-size:10px;background:#061016;border:1px solid #1d3744;color:#b8d0d9}.okbox{border-color:#286b5a!important;color:#aef4e1!important}.errbox{border-color:#913443!important;color:#ffbcc5!important}.busybox{border-color:#916729!important;color:#ffe0a1!important}
#log{height:90px;overflow:auto;margin-top:8px;padding:7px;border-radius:8px;background:#040b10;border:1px solid #18303d;font:9px/1.45 ui-monospace,Consolas,monospace;color:#91b4c1}.controls{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:9px}.hint{margin-top:7px;color:var(--muted);font-size:9px;line-height:1.4}
@media(max-width:950px){#side{width:min(380px,94vw)}#hudLeft{display:none}.hudBottom{transform:translateX(-55%)}}
</style>
</head>
<body>
<div id="app">
<div id="world"></div>
<div id="topbar"><div class="glass pill"><b>VANNIKAWACHH</b> · GCS FLIGHT SIMULATOR</div><div class="glass pill"><span class="online">●</span> <b id="link">HUB CHECKING</b></div></div>
<div id="hud">
  <div id="hudTop" class="glass"><div class="mini">AUTONOMOUS FLIGHT / MISSION MODE</div><div class="hdg" id="hudHdg">HDG 000°</div><div class="tape" id="headingTape">315  330  345  000  015  030  045</div></div>
  <div id="hudLeft" class="glass">
    <div class="label">FLIGHT DATA</div>
    <div class="hudRow"><span>SPD</span><span id="hSpeed" class="hudVal green">0.0 m/s</span></div>
    <div class="hudRow"><span>ALT AGL</span><span id="hAlt" class="hudVal blue">0.0 m</span></div>
    <div class="hudRow"><span>V/S</span><span id="hVs" class="hudVal amber">0.0 m/s</span></div>
    <div class="hudRow"><span>RPM</span><span id="hRpm" class="hudVal">0</span></div>
    <div class="hudRow"><span>BAT</span><span id="hBat" class="hudVal green">100%</span></div>
    <div class="hudRow"><span>GPS</span><span id="hGps" class="hudVal">—</span></div>
  </div>
  <div class="reticle"></div>
  <div id="hudBottom" class="glass">
    <div class="hudMetric"><div class="n" id="bState">IDLE</div><div class="l">MODE</div></div>
    <div class="hudMetric"><div class="n" id="bDist">—</div><div class="l">DIST TO WP</div></div>
    <div class="hudMetric"><div class="n" id="bEta">—</div><div class="l">ETA</div></div>
    <div class="hudMetric"><div class="n" id="bTarget">—</div><div class="l">TARGET</div></div>
  </div>
</div>
<aside id="side" class="glass">
  <div class="title">Mission Planner</div>
  <div class="sub">Ground-control style view for the VanniKawachh autonomous response mission. The flight path and telemetry come from the deployed <b>/drone_state</b> feed.</div>
  <div class="card glass">
    <div class="label">VEHICLE</div>
    <div id="state" class="state green">IDLE</div>
    <div class="row"><span>Vehicle</span><span id="vehicle" class="val">sim0001</span></div>
    <div class="row"><span>Flight mode</span><span id="mode" class="val">IDLE</span></div>
    <div class="row"><span>Mission link</span><span id="missionLink" class="badge green">LIVE HUB</span></div>
  </div>
  <div class="card glass">
    <div class="label">MISSION PLAN</div>
    <div class="mission">
      <div id="wp1" class="wp"><div class="num">1</div><div><div class="wpName">HOME / SAFE LANDING</div><div id="homeMeta" class="wpMeta">—</div></div><span class="badge blue">HOME</span></div>
      <div id="wp2" class="wp"><div class="num">2</div><div><div class="wpName">DISTRESS LOCATION</div><div id="targetMeta" class="wpMeta">—</div></div><span class="badge amber">TARGET</span></div>
      <div id="wp3" class="wp"><div class="num">3</div><div><div class="wpName">HOVER / DELIVERY</div><div class="wpMeta">3 s hover · servo release</div></div><span class="badge">DROP</span></div>
      <div id="wp4" class="wp"><div class="num">4</div><div><div class="wpName">RTL / HOME</div><div class="wpMeta">return and vertical landing</div></div><span class="badge green">RTL</span></div>
    </div>
  </div>
  <div class="card glass">
    <div class="label">TELEMETRY</div>
    <div class="row"><span>GPS</span><span id="gps" class="val">—</span></div>
    <div class="row"><span>Altitude AGL</span><span id="alt" class="val">0.0 m</span></div>
    <div class="row"><span>Ground speed</span><span id="speed" class="val">0.0 m/s</span></div>
    <div class="row"><span>Vertical speed</span><span id="vs" class="val">0.0 m/s</span></div>
    <div class="row"><span>Heading</span><span id="heading" class="val">000°</span></div>
    <div class="row"><span>Motor RPM</span><span id="rpm" class="val">0</span></div>
    <div class="row"><span>Battery</span><span id="battery" class="val">100%</span></div>
    <div class="row"><span>Distance remaining</span><span id="distance" class="val">—</span></div>
    <div class="row"><span>ETA</span><span id="eta" class="val">—</span></div>
  </div>
  <div class="card glass">
    <div class="label">MISSION SEQUENCE</div>
    <div id="sequence" class="mission"></div>
  </div>
  <div class="controls">
    <button id="distress" class="btn primary">TEST DISTRESS</button>
    <button id="live" class="btn">REFRESH HUB</button>
    <button id="fit" class="btn">FIT MISSION</button>
    <button id="follow" class="btn">FOLLOW: OFF</button>
    <button id="topdown" class="btn">TOP DOWN</button>
    <button id="homeView" class="btn warn">HOME VIEW</button>
  </div>
  <div id="status">Initialising GCS…</div>
  <div id="log"></div>
  <div class="hint">Camera: left-drag orbit · right-drag pan · wheel zoom. FOLLOW is soft-follow: it only recenters when the aircraft leaves your view, so you can still inspect the world manually.</div>
</aside>
</div>
<script>
(() => {
  const $=id=>document.getElementById(id);
  const log=m=>{const e=$("log");e.innerHTML+=`<div>${new Date().toLocaleTimeString()} · ${m}</div>`;e.scrollTop=e.scrollHeight};
  const status=(m,k="")=>{const e=$("status");e.textContent=m;e.className=k==='ok'?'okbox':k==='err'?'errbox':k==='busy'?'busybox':''};
  const cart=(lat,lon,h=0)=>Cesium.Cartesian3.fromDegrees(+lon,+lat,+h);
  const dist=(m)=>m==null?'—':m<1000?`${Math.round(m)} m`:`${(m/1000).toFixed(2)} km`;
  const eta=(s)=>s==null||!Number.isFinite(+s)?'—':(+s>=60?`${Math.floor(+s/60)}m ${Math.round(+s)%60}s`:`${Math.round(+s)}s`);
  const phaseLabels={
    ARMING:'Arm / rotor spool',TAKEOFF:'Vertical takeoff',ENROUTE:'Cruise to distress',HOVERING:'Hover at incident',DELIVERING:'Open payload + drop',RTL:'Return to home',LANDING:'Vertical landing',COMPLETED:'Mission complete',FAILED:'Mission failed',IDLE:'Standby'
  };
  const phaseOrder=['ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING','COMPLETED'];
  let viewer,drone,home,target,route,trail,last,lastState='IDLE',timer=null,follow=false,firstMission=true,lastPos=null,lastTime=performance.now(),softFollowMs=0;

  function activeWp(s){
    ['wp1','wp2','wp3','wp4'].forEach(id=>$(id).className='wp');
    if(['IDLE','ARMING','TAKEOFF','ENROUTE'].includes(s))$("wp1").className='wp done';
    if(['ENROUTE'].includes(s))$("wp2").className='wp active';
    if(['HOVERING','DELIVERING'].includes(s))$("wp3").className='wp active';
    if(['RTL','LANDING','COMPLETED'].includes(s)){ $("wp1").className='wp'; $("wp4").className='wp active'; }
    if(s==='COMPLETED')$("wp1").className='wp done';
  }
  function sequence(s){
    const wrap=$("sequence");wrap.innerHTML='';
    const order=['DISTRESS','ARMING','TAKEOFF','ENROUTE','HOVERING','DELIVERING','RTL','LANDING'];
    const current=s==='IDLE'?'IDLE':s;
    order.forEach((x,i)=>{
      const div=document.createElement('div');div.className='wp';
      const done=phaseOrder.indexOf(current)>=phaseOrder.indexOf(x) && current!=='FAILED';
      const active=current===x;
      if(done&&!active)div.classList.add('done');if(active)div.classList.add('active');
      div.innerHTML=`<div class="num">${i+1}</div><div><div class="wpName">${x==='DISTRESS'?'DISTRESS TRIGGER':phaseLabels[x]}</div><div class="wpMeta">${x==='DISTRESS'?'ESP32 / hub event':x==='TAKEOFF'?'climb 0 → 15 m':x==='ENROUTE'?'cruise at 15 m/s':x==='HOVERING'?'hold 3 s':x==='DELIVERING'?'servo + health kit':x==='RTL'?'return to safe home':x==='LANDING'?'15 → 0 m':'ready'}</div></div><span class="badge ${active?'amber':done?'green':'blue'}">${active?'ACTIVE':done?'DONE':'PENDING'}</span>`;
      wrap.appendChild(div);
    });
  }
  function setState(d){
    last=d||{};const s=d?.state||'IDLE';
    $("state").textContent=s;$("state").className='state '+(s==='FAILED'?'red':(['TAKEOFF','ENROUTE','RTL','LANDING'].includes(s)?'amber':'green'));
    $("vehicle").textContent=d?.mission_id||'sim0001';$("mode").textContent=d?.flight_mode||s;
    $("gps").textContent=d?.lat!=null?`${Number(d.lat).toFixed(5)}, ${Number(d.lon).toFixed(5)}`:'—';
    $("alt").textContent=`${Number(d?.altitude_m||0).toFixed(1)} m`;$("speed").textContent=`${Number(d?.speed_ms||0).toFixed(1)} m/s`;
    $("vs").textContent=`${Number(d?.vertical_speed_ms||0).toFixed(1)} m/s`;$("heading").textContent=`${Math.round(Number(d?.heading_deg||0)).toString().padStart(3,'0')}°`;
    $("rpm").textContent=Math.round(Number(d?.motor_rpm||0)).toLocaleString();$("battery").textContent=`${Number(d?.battery_pct ?? 100).toFixed(0)}%`;
    $("distance").textContent=dist(d?.distance_m);$("eta").textContent=eta(d?.eta_reach_s);
    $("hSpeed").textContent=`${Number(d?.speed_ms||0).toFixed(1)} m/s`;$("hAlt").textContent=`${Number(d?.altitude_m||0).toFixed(1)} m`;$("hVs").textContent=`${Number(d?.vertical_speed_ms||0).toFixed(1)} m/s`;$("hRpm").textContent=Math.round(Number(d?.motor_rpm||0)).toLocaleString();$("hBat").textContent=`${Number(d?.battery_pct ?? 100).toFixed(0)}%`;$("hGps").textContent=d?.lat!=null?`${Number(d.lat).toFixed(4)},${Number(d.lon).toFixed(4)}`:'—';$("hudHdg").textContent=`HDG ${Math.round(Number(d?.heading_deg||0)).toString().padStart(3,'0')}°`;
    $("bState").textContent=s;$("bDist").textContent=dist(d?.distance_m);$("bEta").textContent=eta(d?.eta_reach_s);$("bTarget").textContent=d?.target?`${Number(d.target[0]).toFixed(3)}, ${Number(d.target[1]).toFixed(3)}`:'—';
    $("homeMeta").textContent=d?.home?`${Number(d.home[0]).toFixed(5)}, ${Number(d.home[1]).toFixed(5)}`:'—';$("targetMeta").textContent=d?.target?`${Number(d.target[0]).toFixed(5)}, ${Number(d.target[1]).toFixed(5)}`:'waiting for distress';
    $("link").textContent='HUB ONLINE';$("missionLink").textContent='LIVE HUB';sequence(s);activeWp(s);
    if(s!==lastState){log(`STATE → ${s}`);lastState=s}
    if(firstMission&&d?.home){firstMission=false;setTimeout(fitMission,300)}
  }
  function updateEntities(d){
    if(!viewer||d?.lat==null)return;
    drone.position=cart(d.lat,d.lon,d.altitude_m||0);
    if(d.heading_deg!=null)drone.orientation=Cesium.Transforms.headingPitchRollQuaternion(drone.position,new Cesium.HeadingPitchRoll(Cesium.Math.toRadians(d.heading_deg),0,0));
    if(d.home){
      const h=cart(d.home[0],d.home[1],0);if(!home){home=viewer.entities.add({name:'HOME',position:h,point:{pixelSize:12,color:Cesium.Color.CYAN,outlineColor:Cesium.Color.WHITE,outlineWidth:2},label:{text:'HOME / SAFE LANDING',font:'11px sans-serif',showBackground:true,backgroundColor:Cesium.Color.BLACK.withAlpha(.55),pixelOffset:new Cesium.Cartesian2(0,-18)}})}
    }
    if(d.target){
      const t=cart(d.target[0],d.target[1],0);if(!target){target=viewer.entities.add({name:'DISTRESS',position:t,point:{pixelSize:15,color:Cesium.Color.RED,outlineColor:Cesium.Color.WHITE,outlineWidth:2},label:{text:'DISTRESS LOCATION',font:'11px sans-serif',fillColor:Cesium.Color.RED,showBackground:true,backgroundColor:Cesium.Color.BLACK.withAlpha(.55),pixelOffset:new Cesium.Cartesian2(0,-18)}})}
      if(!route&&d.home){route=viewer.entities.add({name:'MISSION ROUTE',polyline:{positions:[cart(d.home[0],d.home[1],15),cart(d.target[0],d.target[1],15),cart(d.home[0],d.home[1],15)],width:4,material:Cesium.Color.CYAN}})}
    }
    if(!trail){trail=viewer.entities.add({name:'FLIGHT TRAIL',polyline:{positions:[],width:2,material:Cesium.Color.LIME.withAlpha(.85)}})}
    const arr=trail.polyline.positions.getValue(Cesium.JulianDate.now())||[];arr.push(drone.position);if(arr.length>500)arr.shift();trail.polyline.positions=arr;
    if(follow){const now=performance.now();if(now-softFollowMs>1200){const win=Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene,drone.position,new Cesium.Cartesian2());const inside=win&&win.x>viewer.canvas.clientWidth*.15&&win.x<viewer.canvas.clientWidth*.85&&win.y>viewer.canvas.clientHeight*.15&&win.y<viewer.canvas.clientHeight*.85;if(!inside){viewer.camera.flyTo({destination:Cesium.Cartesian3.add(drone.position,new Cesium.Cartesian3(0,0,120),new Cesium.Cartesian3()),duration:.7});softFollowMs=now}}}
  }
  function fitMission(){if(!last?.home)return;const points=[];points.push(cart(last.home[0],last.home[1],0));if(last.target)points.push(cart(last.target[0],last.target[1],15));const rect=points.length>1?Cesium.Rectangle.fromCartesianArray(points):Cesium.Rectangle.fromCartographicArray([Cesium.Cartographic.fromDegrees(last.home[1],last.home[0])]);viewer.camera.flyTo({destination:rect,duration:1.1});status('Mission fitted — free camera','ok')}
  function homeView(){if(last?.home){viewer.camera.flyTo({destination:cart(last.home[0],last.home[1],500),orientation:{heading:0,pitch:Cesium.Math.toRadians(-45),roll:0},duration:.9});status('Home / launch view','ok')}}
  function topDown(){if(last?.home){const lat=(last.home[0]+(last.target?.[0]||last.home[0]))/2;const lon=(last.home[1]+(last.target?.[1]||last.home[1]))/2;viewer.camera.flyTo({destination:cart(lat,lon,Math.max(1200,Number(last.distance_m||1000)*1.4)),orientation:{heading:0,pitch:Cesium.Math.toRadians(-90),roll:0},duration:.9});status('Top-down mission view','ok')}}
  async function hub(){try{const r=await fetch('/drone_state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);const d=await r.json();setState(d);updateEntities(d);status('Hub telemetry live','ok');return d}catch(e){$("link").textContent='HUB ERROR';status(`Hub error: ${e.message}`,'err');return null}}
  async function distress(){const b=$("distress");b.disabled=true;status('Dispatching test distress…','busy');try{const r=await fetch('/node-alert?node=WEB-GCS&lat=21.128&lon=79.047&event=1&conf=0.99&pir=1&light=30',{cache:'no-store'});const t=await r.text();if(!r.ok)throw new Error(`HTTP ${r.status}: ${t}`);log(`DISTRESS → ${t}`);await hub();status('Mission dispatched','ok')}catch(e){status(`Dispatch failed: ${e.message}`,'err');log(`ERROR → ${e.message}`)}finally{setTimeout(()=>b.disabled=false,800)}}
  async function init(){
    viewer=new Cesium.Viewer('world',{imageryProvider:new Cesium.UrlTemplateImageryProvider({url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png',credit:'© OpenStreetMap contributors'}),terrainProvider:new Cesium.EllipsoidTerrainProvider(),baseLayerPicker:false,geocoder:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,animation:false,timeline:false,fullscreenButton:false,infoBox:false,selectionIndicator:false,shouldAnimate:true});
    viewer.scene.globe.enableLighting=true;viewer.scene.screenSpaceCameraController.enableZoom=true;viewer.scene.screenSpaceCameraController.enableRotate=true;viewer.scene.screenSpaceCameraController.enableTranslate=true;viewer.scene.screenSpaceCameraController.enableTilt=true;viewer.scene.screenSpaceCameraController.enableLook=true;
    try{viewer.scene.primitives.add(await Cesium.createOsmBuildingsAsync())}catch(_){log('3D buildings unavailable; continuing with OSM surface')}
    drone=viewer.entities.add({name:'VanniKawachh UAV',position:cart(21.1466,79.0889,0),model:{uri:'https://cdn.jsdelivr.net/gh/amvlab/aircraft-models@main/models/drone_nologo.glb',minimumPixelSize:95,maximumScale:220,scale:1.2,shadows:Cesium.ShadowMode.ENABLED}});
    await hub();homeView();
    timer=setInterval(hub,700);
  }
  $("distress").onclick=distress;$("live").onclick=hub;$("fit").onclick=fitMission;$("homeView").onclick=homeView;$("topdown").onclick=topDown;
  $("follow").onclick=()=>{follow=!follow;$("follow").textContent=`FOLLOW: ${follow?'ON':'OFF'}`;status(follow?'Soft-follow enabled — camera remains user movable':'Free camera restored','ok');if(follow&&last?.lat!=null)homeView()};
  window.addEventListener('keydown',e=>{if(e.key.toLowerCase()==='f')fitMission();if(e.key.toLowerCase()==='h')homeView();if(e.key.toLowerCase()==='t')topDown()});
  init().catch(e=>{status(`Viewer failed: ${e.message}`,'err');log(`INIT ERROR → ${e.message}`)});
})();
</script>
</body>
</html>'''
