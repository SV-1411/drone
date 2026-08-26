"""Clean phased visual drone simulator with shared rotor telemetry."""
from __future__ import annotations
import math, threading, time

def haversine_m(a,b):
    R=6371000.0; p1,p2=math.radians(a[0]),math.radians(b[0]); dp=math.radians(b[0]-a[0]); dl=math.radians(b[1]-a[1])
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(max(0.0,x)))

def bearing(a,b):
    p1,p2=math.radians(a[0]),math.radians(b[0]); dl=math.radians(b[1]-b[1]) if False else math.radians(b[1]-a[1])
    return (math.degrees(math.atan2(math.sin(dl)*math.cos(p2),math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl)))+360)%360

def interp(a,b,f): return a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f

class PhysicalSimDrone:
    def __init__(self,lat,lon,speed_ms=15.0,name="Base"):
        self.lock=threading.RLock(); self.base=(float(lat),float(lon)); self.speed=max(1.0,float(speed_ms)); self.name=name
        self.counter=0; self.generation=0; self.state="IDLE"; self.mission_id=None; self.lat,self.lon=self.base
        self.altitude_m=0.0; self.vertical_speed_ms=0.0; self.ground_speed_ms=0.0; self.heading_deg=0.0; self.target=None; self.kit_dropped=False
        self.node_name=""; self.started_at=None; self.eta_reach_s=0.0; self.distance_m=0.0; self.battery_pct=100.0
    def rpm(self): return {"IDLE":0,"ARMING":1800,"TAKEOFF":4600,"ENROUTE":5000,"HOVERING":4300,"DELIVERING":4000,"RTL":5000,"LANDING":3000}.get(self.state,0)
    def snapshot(self):
        with self.lock:
            return {"state":self.state,"mission_id":self.mission_id,"name":self.name,"lat":self.lat,"lon":self.lon,"home":[*self.base],"target":self.target,"available":self.state in ("IDLE","COMPLETED","FAILED"),"kit_dropped":self.kit_dropped,"node_name":self.node_name,"eta_reach_s":round(max(0,self.eta_reach_s)),"distance_m":round(max(0,self.distance_m)),"speed_ms":round(self.ground_speed_ms,2),"ground_speed_ms":round(self.ground_speed_ms,2),"vertical_speed_ms":round(self.vertical_speed_ms,2),"altitude_m":round(self.altitude_m,2),"heading_deg":round(self.heading_deg,1),"battery_pct":round(self.battery_pct,1),"motor_rpm":self.rpm(),"flight_elapsed_s":round(time.time()-self.started_at,1) if self.started_at else 0.0,"flight_mode":self.state}
    def dispatch(self,lat,lon,priority="high",node_name=""):
        with self.lock:
            if self.state not in ("IDLE","COMPLETED","FAILED"): return self.mission_id
            self.counter+=1; self.generation+=1; g=self.generation; self.mission_id=f"sim{self.counter:04d}"; self.target=[float(lat),float(lon)]; self.node_name=node_name
            self.kit_dropped=False; self.started_at=time.time(); self.state="ARMING"; self.vertical_speed_ms=0; self.ground_speed_ms=0; self.altitude_m=0; self.heading_deg=bearing(self.base,(float(lat),float(lon))); self.distance_m=haversine_m(self.base,(float(lat),float(lon))); self.eta_reach_s=self.distance_m/self.speed+14; self.battery_pct=100
        threading.Thread(target=self._run,args=(g,),daemon=True).start(); return self.mission_id
    def _active(self,g): return self.generation==g
    def _set(self,g,**kw):
        with self.lock:
            if self.generation!=g: return False
            for k,v in kw.items(): setattr(self,k,v)
            return True
    def _climb(self,g,target,seconds):
        start=self.altitude_m; delta=target-start; t=time.time()
        while True:
            f=min(1,(time.time()-t)/seconds); self._set(g,altitude_m=start+delta*f,vertical_speed_ms=(delta/seconds) if f<1 else 0.0,ground_speed_ms=0)
            if f>=1:return
            time.sleep(.05)
    def _travel(self,g,start,end,seconds,state,alt):
        seconds=max(2.0,float(seconds)); t=time.time()
        while True:
            f=min(1,(time.time()-t)/seconds); lat,lon=interp(start,end,f); left=haversine_m((lat,lon),end)
            self._set(g,lat=lat,lon=lon,altitude_m=alt,vertical_speed_ms=0.0,ground_speed_ms=self.speed,heading_deg=bearing(start,end),state=state,distance_m=left,eta_reach_s=left/self.speed)
            if f>=1:return
            time.sleep(.05)
    def _run(self,g):
        target=tuple(self.target); alt=15.0
        try:
            time.sleep(1.2); self._set(g,state="TAKEOFF"); self._climb(g,alt,4)
            if not self._active(g):return
            self._travel(g,self.base,target,haversine_m(self.base,target)/self.speed,"ENROUTE",alt)
            if not self._active(g):return
            self._set(g,state="HOVERING",ground_speed_ms=0,vertical_speed_ms=0,distance_m=0,eta_reach_s=0); time.sleep(3)
            if not self._active(g):return
            self._set(g,state="DELIVERING",ground_speed_ms=0,vertical_speed_ms=0); time.sleep(2); self._set(g,kit_dropped=True); time.sleep(1)
            self._travel(g,target,self.base,haversine_m(target,self.base)/self.speed,"RTL",alt)
            if not self._active(g):return
            self._set(g,state="LANDING",ground_speed_ms=0,distance_m=0,eta_reach_s=0); self._climb(g,0,4)
            self._set(g,state="COMPLETED",lat=self.base[0],lon=self.base[1],altitude_m=0,vertical_speed_ms=0,ground_speed_ms=0,distance_m=0,eta_reach_s=0)
        except Exception:self._set(g,state="FAILED",vertical_speed_ms=0,ground_speed_ms=0)

class PhysicalFleet:
    def __init__(self,bases,speed_ms=15.0): self.drones=[PhysicalSimDrone(la,lo,speed_ms,nm) for nm,la,lo in bases]; self.last_drone=None
    def _nearest(self,lat,lon): return min(self.drones,key=lambda d:haversine_m(d.base,(lat,lon)))
    def eta(self,lat,lon):
        d=self._nearest(lat,lon); dist=haversine_m(d.base,(lat,lon)); return {"drone":d.name,"distance_m":round(dist),"eta_reach_s":round(dist/d.speed),"eta_total_s":round(dist/d.speed+14)}
    def dispatch(self,lat,lon,priority="high",node_name=""): d=self._nearest(lat,lon); self.last_drone=d.name; return d.dispatch(lat,lon,priority,node_name)
    def active(self):
        a=[d for d in self.drones if not d.snapshot()["available"]]; return (a[-1] if a else self.drones[0]).snapshot()
    def snapshots(self): return [d.snapshot() for d in self.drones]
class PhysicalDispatcher:
    def __init__(self,fleet): self.fleet=fleet
    def dispatch(self,lat,lon,priority="normal",node_name=""): return self.fleet.dispatch(lat,lon,priority,node_name)
