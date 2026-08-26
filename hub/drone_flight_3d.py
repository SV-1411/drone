"""Stable Cesium 3D geographic drone flight viewer.

The browser layer consumes /drone_state. It is intentionally independent of
SIMNET and does not reposition the camera during ordinary telemetry updates.
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
<title>VanniKawachh | 3D Drone Flight</title>
<link rel="stylesheet" href="https://cesium.com/downloads/cesiumjs/releases/1.132/Build/Cesium/Widgets/widgets.css">
<style>
:root{--bg:#071018;--panel:#08141de8;--line:#274451;--text:#edf7fa;--muted:#8da5b4;--green:#32e0b0;--amber:#ffb24a;--red:#ff6875;--blue:#69b5ff}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:12px Inter,Segoe UI,Arial,sans-serif}
#app{position:relative;width:100vw;height:100vh}#world{position:absolute;inset:0}#cesium{position:absolute;inset:0}
.glass{background:var(--panel);border:1px solid var(--line);box-shadow:0 12px 35px #0008;backdrop-filter:blur(8px)}
#top{position:absolute;z-index:20;top:12px;left:12px;right:12px;display:flex;justify-content:space-between;pointer-events:none}.pill{padding:8px 12px;border-radius:999px}.live{color:var(--green)}
#hudTop{position:absolute;z-index:15;left:50%;top:14px;transform:translateX(-50%);padding:7px 18px;border-radius:10px;text-align:center;min-width:360px;pointer-events:none}.small{font-size:9px;color:var(--muted);letter-spacing:.14em}.hdg{font-size:22px;font-weight:900}.tape{font:700 10px ui-monospace,Consolas,monospace;letter-spacing:.12em}
#hudLeft{position:absolute;z-index:15;left:14px;top:75px;width:220px;padding:10px;border-radius:10px;pointer-events:none}.hrow{display:flex;justify-content:space-between;margin:7px 0}.hv{font-weight:900}.green{color:var(--green)}.amber{color:var(--amber)}.blue{color:var(--blue)}
#reticle{position:absolute;z-index:14;left:50%;top:50%;transform:translate(-50%,-50%);width:48px;height:48px;border:1px solid #9de9ff88;border-radius:50%;pointer-events:none}.reticle-line{position:absolute;background:#9de9ff88}.rh{width:72px;height:1px;left:-13px;top:23px}.rv{width:1px;height:72px;left:23px;top:-13px}
#side{position:absolute;z-index:30;right:12px;top:64px;width:390px;bottom:12px;overflow:auto;padding:11px;border-radius:14px}.title{font-size:20px;font-weight:900}.sub,.note{font-size:10px;line-height:1.45;color:var(--muted)}
.card{margin-top:9px;padding:10px;border-radius:10px}.label{font-size:9px;font-weight:900;letter-spacing:.14em;color:var(--muted);margin-bottom:6px}.state{font-size:29px;font-weight:900}.row{display:flex;justify-content:space-between;gap:8px;margin:7px 0}.val{font-weight:800;text-align:right}
.seq{display:grid;gap:4px}.step{padding:7px;border:1px solid #1d3440;border-radius:8px;color:#667e8b;background:#09151d}.step.active{border-color:#916729;background:#221a10;color:#ffdda3;font-weight:900}.step.done{border-color:#286a58;background:#0b211b;color:#acf3df}
.wp{display:grid;grid-template-columns:28px 1fr auto;gap:8px;align-items:center;padding:7px;border:1px solid #1d3440;border-radius:8px;margin-bottom:5px}.num{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;border:1px solid #44606b;font-weight:900}.wp.active{border-color:#93672b;background:#221a10}.wp.done{border-color:#286a58;background:#0b211b}.wpname{font-weight:900}.meta{font-size:9px;color:var(--muted)}.badge{font-size:8px;padding:3px 6px;border-radius:999px;border:1px solid #35505e}.badge.green{color:var(--green);border-color:#286a58}.badge.red{color:var(--red);border-color:#73313c}.badge.blue{color:var(--blue);border-color:#355f7c}
.buttons{display:grid;grid-template-columns:1fr 1fr;gap:6px}.btn{border:1px solid var(--line);background:#122431;color:#fff;padding:9px;border-radius:8px;font-weight:900;cursor:pointer}.btn.primary{background:#0e2d25;border-color:#286d5a}.btn.warn{background:#2a2114;border-color:#705126}.btn:disabled{opacity:.45;cursor:wait}
#status{margin-top:8px;padding:8px;border:1px solid #1d3744;background:#061016;border-radius:8px;font-size:10px}#log{height:90px;overflow:auto;margin-top:8px;padding:7px;border:1px solid #18313e;background:#040b10;border-radius:8px;font:9px/1.4 ui-monospace,Consolas,monospace;color:#8fb7c5}
@media(max-width:950px){#side{width:min(390px,94vw)}}
</style>
</head>
<body>
<div id="app">
  <div id="world"><div id="cesium"></div></div>
  <div id="top"><div class="glass pill"><b>VANNIKAWACHH</b> · 3D AUTONOMOUS DRONE FLIGHT</div><div class="glass pill"><span class="live">●</span> <b id="link">HUB CHECKING</b></div></div>
  <div id="hudTop" class="glass"><div class="small">AUTONOMOUS FLIGHT / GCS VIEW</div><div class="hdg" id="hdg">HDG 000°</div><div class="tape" id="tape">315 330 345 000 015 030 045</div></div>
  <div id="hudLeft" class="glass"><div class="label">LIVE FLIGHT DATA</div><div class="hrow"><span>SPD</span><span id="hspd" class="hv green">0.0 m/s</span></div><div class="hrow"><span>ALT AGL</span><span id="halt" class="hv blue">0.0 m</span></div><div class="hrow"><span>V/S</span><span id="hvs" class="hv amber">0.0 m/s</span></div><div class="hrow"><span>RPM</span><span id="hrpm" class="hv">0</span></div><div class="hrow"><span>BAT</span><span id="hbat" class="hv green">100%</span></div></div>
  <div id="reticle"><div class="reticle-line rh"></div><div class="reticle-line rv"></div></div>
  <aside id="side" class="glass">
    <div class="title">Mission Planner</div><div class="sub">Real-time geographic presentation driven by the same Wokwi/ESP32 → hub → /drone_state pipeline. The browser camera is independent of telemetry updates.</div>
    <div class="card glass"><div class="label">VEHICLE</div><div id="state" class="state green">IDLE</div><div class="row"><span>Mission</span><span id="mission" class="val">—</span></div><div class="row"><span>GPS</span><span id="gps" class="val">—</span></div><div class="row"><span>Mode</span><span id="mode" class="val">IDLE</span></div><div class="row"><span>Battery</span><span id="battery" class="val">100%</span></div></div>
    <div class="card glass"><div class="label">MISSION PLAN</div>
      <div id="wp1" class="wp"><div class="num">1</div><div><div class="wpname">HOME / SAFE LANDING</div><div id="homeMeta" class="meta">—</div></div><span class="badge blue">HOME</span></div>
      <div id="wp2" class="wp"><div class="num">2</div><div><div class="wpname">DISTRESS LOCATION</div><div id="targetMeta" class="meta">—</div></div><span class="badge red">TARGET</span></div>
      <div id="wp3" class="wp"><div class="num">3</div><div><div class="wpname">HOVER / DELIVERY</div><div class="meta">hover 3 s · open bay · drop kit</div></div><span class="badge">DROP</span></div>
      <div id="wp4" class="wp"><div class="num">4</div><div><div class="wpname">RTL / LAND</div><div class="meta">return to home · vertical descent</div></div><span class="badge green">RTL</span></div>
    </div>
    <div class="card glass"><div class="label">TELEMETRY</div><div class="row"><span>Speed</span><span id="speed" class="val">0.0 m/s</span></div><div class="row"><span>Altitude AGL</span><span id="alt" class="val">0.0 m</span></div><div class="row"><span>Vertical speed</span><span id="vs" class="val">0.0 m/s</span></div><div class="row"><span>Heading</span><span id="heading" class="val">000°</span></div><div class="row"><span>Motor RPM</span><span id="rpm" class="val">0</span></div><div class="row"><span>Distance</span><span id="distance" class="val">—</span></div><div class="row"><span>ETA</span><span id="eta" class="val">—</span></div></div>
    <div class="card glass"><div class="label">MISSION SEQUENCE</div><div id="sequence" class="seq"></div></div>
    <div class="buttons"><button id="distress" class="btn primary">TEST DISTRESS</button><button id="live" class="btn">REFRESH HUB</button><button id="fit" class="btn">FIT MISSION</button><button id="follow" class="btn">FOLLOW: OFF</button><button id="topdown" class="btn">TOP DOWN</button><button id="homeView" class="btn warn">HOME VIEW</button></div>
    <div id="status">Loading 3D world…</div><div id="log"></div><div class="note">Camera: left-drag orbit · right-drag pan · wheel zoom. The viewer never repositions the camera just because telemetry changed. <b>FOLLOW</b> is an explicit mode.</div>
  </aside>
</div>
<script>
(function(){
  function loadCesium(){
    if(window.Cesium){start();return;}
    var s=document.createElement('script');
    s.src='https://cesium.com/downloads/cesiumjs/releases/1.132/Build/Cesium/Cesium.js';
    s.onload=start;
    s.onerror=function(){
      var f=document.createElement('script');
      f.src='https://cdn.jsdelivr.net/npm/cesium@1.132.0/Build/Cesium/Cesium.js';
      f.onload=start;
      f.onerror=function(){setStatus('Cesium failed to load from both CDNs','err');};
      document.head.appendChild(f);
    };
    document.head.appendChild(s);
  }
  var viewer,drone,homeEntity,targetEntity,routeEntity,trailEntity,trail=[],lastState='IDLE',lastMission=null,follow=false,lastPoll=0;
  var $=function(id){return document.getElementById(id)};
  function setStatus(m,k){$('status').textContent=m;$('status').style.color=k==='err'?'#ffbcc5':k==='ok'?'#aef4e1':k==='busy'?'#ffe0a1':''}
  function log(m){var e=$('log');e.innerHTML+='<div>'+new Date().toLocaleTimeString()+' · '+m+'</div>';e.scrollTop=e.scrollHeight}
  function cart(lat,lon,h){return Cesium.Cartesian3.fromDegrees(Number(lon),Number(lat),Number(h||0))}
  function fmtDist(m){return m==null?'—':m<1000?Math.round(m)+' m':(m/1000).toFixed(2)+' km'}
  function fmtEta(s){return s==null?'—':s>=60?Math.floor(s/60)+'m '+Math.round(s%60)+'s':Math.round(s)+'s'}
  function bearing(a,b){var p1=Cesium.Math.toRadians(a[0]),p2=Cesium.Math.toRadians(b[0]),dl=Cesium.Math.toRadians(b[1]-a[1]);return Math.atan2(Math.sin(dl)*Math.cos(p2),Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(dl))}
  function hpr(q){return Cesium.Transforms.headingPitchRollQuaternion(q, new Cesium.HeadingPitchRoll(0,0,0))}
  function setWp(s){['wp1','wp2','wp3','wp4'].forEach(function(id){$(id).className='wp'});if(['IDLE','ARMING','TAKEOFF'].indexOf(s)>=0)$('wp1').className='wp done';if(s==='ENROUTE')$('wp2').className='wp active';if(['HOVERING','DELIVERING'].indexOf(s)>=0)$('wp3').className='wp active';if(['RTL','LANDING'].indexOf(s)>=0)$('wp4').className='wp active';if(s==='COMPLETED')$('wp4').className='wp done'}
  function buildSequence(s){var labels=['Distress trigger received','Arm / rotor spool','Vertical takeoff','Cruise to distress GPS','Hover at incident','Open payload bay','Drop health kit','RTL / land'];var active={'ARMING':1,'TAKEOFF':2,'ENROUTE':3,'HOVERING':4,'DELIVERING':6,'RTL':7,'LANDING':7}[s]||0;var done=phaseIndex(s);$('sequence').innerHTML=labels.map(function(x,i){var cls=i<done?'step done':(i===active?'step active':'step');return '<div class="'+cls+'">'+(i<done?'●':'○')+' '+x+'</div>'}).join('')}
  function phaseIndex(s){return {'IDLE':0,'ARMING':1,'TAKEOFF':2,'ENROUTE':4,'HOVERING':5,'DELIVERING':7,'RTL':8,'LANDING':8,'COMPLETED':8}[s]||0}
  function apply(d){if(!d||!viewer)return;var s=d.state||'IDLE';$('state').textContent=s;$('state').className='state '+(s==='FAILED'?'bad':(['TAKEOFF','ENROUTE','RTL','LANDING'].indexOf(s)>=0?'amber':'green'));$('mission').textContent=d.mission_id||'—';$('mode').textContent=d.flight_mode||s;$('gps').textContent=d.lat!=null?Number(d.lat).toFixed(5)+', '+Number(d.lon).toFixed(5):'—';$('speed').textContent=Number(d.speed_ms||0).toFixed(1)+' m/s';$('alt').textContent=Number(d.altitude_m||0).toFixed(1)+' m';$('vs').textContent=Number(d.vertical_speed_ms||0).toFixed(2)+' m/s';$('heading').textContent=Math.round(Number(d.heading_deg||0)).toString().padStart(3,'0')+'°';$('rpm').textContent=Math.round(Number(d.motor_rpm||0)).toLocaleString();$('distance').textContent=fmtDist(d.distance_m);$('eta').textContent=fmtEta(d.eta_reach_s);$('battery').textContent=Number(d.battery_pct==null?100:d.battery_pct).toFixed(0)+'%';$('hspd').textContent=Number(d.speed_ms||0).toFixed(1)+' m/s';$('halt').textContent=Number(d.altitude_m||0).toFixed(1)+' m';$('hvs').textContent=Number(d.vertical_speed_ms||0).toFixed(2)+' m/s';$('hrpm').textContent=Math.round(Number(d.motor_rpm||0)).toLocaleString();$('hbat').textContent=Number(d.battery_pct==null?100:d.battery_pct).toFixed(0)+'%';$('hdg').textContent='HDG '+Math.round(Number(d.heading_deg||0)).toString().padStart(3,'0')+'°';$('tape').textContent='315  330  345  '+Math.round(Number(d.heading_deg||0)).toString().padStart(3,'0')+'  015  030  045';$('link').textContent='HUB ONLINE';setWp(s);buildSequence(s);if(s!==lastState){log('STATE → '+s);lastState=s}if(d.mission_id!==lastMission){lastMission=d.mission_id; if(d.mission_id)log('MISSION '+d.mission_id);if(d.mission_id)fitMission(false)}if(d.home&&d.target&&d.lat!=null){var h=cart(d.home[0],d.home[1],0),ha=cart(d.home[0],d.home[1],15),ta=cart(d.target[0],d.target[1],15),tg=cart(d.target[0],d.target[1],0);homeEntity.position=h;targetEntity.position=tg;routeEntity.polyline.positions=[h,ha,ta,tg,h];drone.position=cart(d.lat,d.lon,d.altitude_m||0);drone.orientation=Cesium.Transforms.headingPitchRollQuaternion(drone.position,new Cesium.HeadingPitchRoll(Cesium.Math.toRadians(Number(d.heading_deg||bearing(d.home,d.target)*180/Math.PI)),0,0));trail.push(drone.position);if(trail.length>400)trail.shift();trailEntity.polyline.positions=trail.slice();if(follow){var now=performance.now();if(now-lastPoll>1200){lastPoll=now;viewer.flyTo(drone,{duration:0.8,offset:new Cesium.HeadingPitchRange(Cesium.Math.toRadians(25),Cesium.Math.toRadians(-28),650)});}}}}
  function fitMission(animate){if(!homeEntity||!targetEntity||!drone)return;var entities=[homeEntity,targetEntity,drone];viewer.flyTo(entities,{duration:animate===false?0:1.7,offset:new Cesium.HeadingPitchRange(Cesium.Math.toRadians(20),Cesium.Math.toRadians(-35),Math.max(900,Math.min(12000,Math.max(1200,(last&&last.distance_m||2000)*1.1))) )});}
  function homeView(){if(last&&last.home)viewer.camera.flyTo({destination:cart(last.home[0],last.home[1],700),orientation:{heading:0,pitch:Cesium.Math.toRadians(-35),roll:0},duration:1.1})}
  async function poll(){try{var r=await fetch('/drone_state',{cache:'no-store'});var d=await r.json();apply(d);setStatus('LIVE HUB · telemetry '+new Date().toLocaleTimeString(),'ok')}catch(e){$('link').textContent='HUB OFFLINE';setStatus('Hub telemetry unavailable','err');}setTimeout(poll,700)}
  async function trigger(){var b=$('distress');b.disabled=true;setStatus('Dispatching test distress…','busy');try{var r=await fetch('/node-alert?node=WEB-FLIGHT&lat=21.15786&lon=79.08939&event=1&conf=0.99&pir=1&light=25');var j=await r.json();log('TEST DISTRESS → '+(j.mission_id||j.drone||'accepted'));setStatus('Distress accepted · mission '+(j.mission_id||'created'),'ok');fitMission(true)}catch(e){log('TEST DISTRESS ERROR → '+e);setStatus('Distress request failed','err')}b.disabled=false}
  function start(){try{viewer=new Cesium.Viewer('cesium',{animation:false,timeline:false,geocoder:false,homeButton:false,sceneModePicker:false,baseLayerPicker:false,navigationHelpButton:false,infoBox:false,selectionIndicator:false,fullscreenButton:false,shouldAnimate:false});viewer.scene.screenSpaceCameraController.enableRotate=true;viewer.scene.screenSpaceCameraController.enableZoom=true;viewer.scene.screenSpaceCameraController.enableTranslate=true;viewer.scene.screenSpaceCameraController.enableTilt=true;viewer.scene.screenSpaceCameraController.enableLook=true;viewer.scene.screenSpaceCameraController.minimumZoomDistance=80;viewer.scene.screenSpaceCameraController.maximumZoomDistance=30000000;viewer.scene.globe.enableLighting=true;viewer.imageryLayers.removeAll();viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png',credit:'© OpenStreetMap contributors'}));viewer.scene.globe.depthTestAgainstTerrain=false;try{Cesium.createOsmBuildingsAsync().then(function(b){viewer.scene.primitives.add(b)}).catch(function(){})}catch(e){}
    var modelUrl='https://cdn.jsdelivr.net/gh/amvlab/aircraft-models@main/models/drone.glb';
    drone=viewer.entities.add({name:'VanniKawachh UAV',position:cart(21.15786,79.08939,0),model:{uri:modelUrl,scale:2.1,minimumPixelSize:90,maximumScale:5000},label:{text:'VANNIKAWACHH UAV',font:'12px sans-serif',fillColor:Cesium.Color.WHITE,outlineColor:Cesium.Color.BLACK,outlineWidth:3,style:Cesium.LabelStyle.FILL_AND_OUTLINE,verticalOrigin:Cesium.VerticalOrigin.BOTTOM,pixelOffset:new Cesium.Cartesian2(0,-35)}});
    homeEntity=viewer.entities.add({name:'HOME',position:cart(21.1188,79.0195,0),point:{pixelSize:10,color:Cesium.Color.CYAN,outlineColor:Cesium.Color.WHITE,outlineWidth:2},label:{text:'SAFE LANDING / HOME',font:'11px sans-serif',fillColor:Cesium.Color.CYAN,outlineColor:Cesium.Color.BLACK,outlineWidth:3,style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(0,-15)}});
    targetEntity=viewer.entities.add({name:'DISTRESS',position:cart(21.15786,79.08939,0),point:{pixelSize:14,color:Cesium.Color.RED,outlineColor:Cesium.Color.WHITE,outlineWidth:2},label:{text:'DISTRESS',font:'11px sans-serif',fillColor:Cesium.Color.RED,outlineColor:Cesium.Color.BLACK,outlineWidth:3,style:Cesium.LabelStyle.FILL_AND_OUTLINE,pixelOffset:new Cesium.Cartesian2(0,-18)}});
    routeEntity=viewer.entities.add({name:'MISSION ROUTE',polyline:{positions:[cart(21.1188,79.0195,0),cart(21.1188,79.0195,15),cart(21.15786,79.08939,15),cart(21.15786,79.08939,0),cart(21.1188,79.0195,0)],width:4,material:Cesium.Color.CYAN.withAlpha(.7)}});
    trailEntity=viewer.entities.add({name:'LIVE TRAIL',polyline:{positions:[],width:3,material:Cesium.Color.YELLOW.withAlpha(.55)}});
    viewer.camera.setView({destination:cart(21.138,79.055,2500),orientation:{heading:0,pitch:Cesium.Math.toRadians(-35),roll:0}});log('Cesium 3D world ready');setStatus('3D world ready · waiting for mission','ok');poll();
  }catch(e){console.error(e);setStatus('Viewer failed: '+e.message,'err');}}
  $('distress').onclick=trigger;$('live').onclick=function(){poll()};$('fit').onclick=function(){fitMission(true)};$('follow').onclick=function(){follow=!follow;$('follow').textContent='FOLLOW: '+(follow?'ON':'OFF');if(follow)fitMission(true)};$('topdown').onclick=function(){if(last&&last.lat!=null)viewer.camera.flyTo({destination:cart(last.lat,last.lon,5000),orientation:{heading:0,pitch:Cesium.Math.toRadians(-90),roll:0},duration:1})};$('homeView').onclick=homeView;
  loadCesium();
})();
</script>
</body>
</html>'''
