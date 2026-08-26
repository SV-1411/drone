#!/usr/bin/env python3
"""Prepare an F450 visual model for ArduPilot Gazebo Harmonic."""
from __future__ import annotations
import copy, re, shutil, sys, xml.etree.ElementTree as ET
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "third_party" / "px4-quadrotor-HW-parts" / "custom_f450"
DST = Path.home() / "ardupilot_gazebo" / "models" / "vannikawachh_f450"
def q(tag: str, text: str | None = None, **attrs):
    e = ET.Element(tag, attrs)
    if text is not None: e.text = text
    return e
def find_model_sdf(src: Path) -> Path:
    for p in (src / "model.sdf", src / "custom_f450.sdf"):
        if p.exists(): return p
    found = sorted(src.rglob("*.sdf"))
    if not found: raise FileNotFoundError(f"No SDF model found below {src}")
    return found[0]
def clean_plugins(model: ET.Element):
    for parent in model.iter():
        for child in list(parent):
            if child.tag != "plugin": continue
            blob = ((child.get("name") or "") + " " + (child.get("filename") or "")).lower()
            if any(k in blob for k in ("mavlink","px4","motor_model","gazebo_motor","gazebo_ros","ros_control","liblift","lift_drag","ardupilotplugin")):
                parent.remove(child)
def get_rotors(root: ET.Element):
    joints=[]
    for joint in root.iter("joint"):
        name=joint.get("name","")
        if re.search(r"rotor_[0-3]_joint$", name):
            child=joint.find("child"); child_name=child.text.strip() if child is not None and child.text else name.replace("_joint","")
            joints.append((name,child_name))
    if len(joints)!=4: raise RuntimeError(f"Expected four rotor joints, found {joints}")
    joints.sort(key=lambda x:int(re.search(r"rotor_(\d+)_joint",x[0]).group(1)))
    return joints
def get_base_link(root: ET.Element):
    names=[l.get("name") for l in root.findall("link") if l.get("name")]
    for p in ("base_link","base","body"):
        if p in names: return p
    if names: return names[0]
    raise RuntimeError("No top-level link found in F450 model")
def find_imu(root: ET.Element, model_name: str):
    for link in root.iter("link"):
        lname=link.get("name")
        if not lname: continue
        for sensor in link.findall("sensor"):
            if sensor.get("type")=="imu": return f"{model_name}::{lname}::{sensor.get('name','imu_sensor')}"
    return None
def ensure_imu(root: ET.Element, model_name: str, base_link: str) -> str:
    existing=find_imu(root,model_name)
    if existing: return existing
    link=next((x for x in root.iter("link") if x.get("name")==base_link),None)
    if link is None: raise RuntimeError(f"Could not locate base link {base_link} to add IMU")
    sensor=q("sensor",name="vanni_imu",type="imu")
    sensor.append(q("always_on","1")); sensor.append(q("update_rate","400"))
    imu=q("imu")
    for block_name in ("angular_velocity","linear_acceleration"):
        block=q(block_name)
        for axis in ("x","y","z"):
            a=q(axis); noise=q("noise", type="gaussian")
            noise.append(q("mean","0")); noise.append(q("stddev","0.0005"))
            a.append(noise); block.append(a)
        imu.append(block)
    sensor.append(imu); link.append(sensor)
    return f"{model_name}::{base_link}::vanni_imu"
def normalize_poses(root: ET.Element):
    """Convert legacy 3-value poses to SDF 6-value poses when the pose is Euler/RPY."""
    for pose in root.iter("pose"):
        text=(pose.text or "").strip()
        vals=text.split()
        rotation_format=pose.get("rotation_format")
        if rotation_format in (None,"euler_rpy") and len(vals)==3:
            pose.text=text+" 0 0 0"
def add_payload(root: ET.Element, base_link: str):
    if any(x.get("name")=="payload_drop_joint" for x in root.findall("joint")): return
    link=q("link",name="vanni_payload_drop"); inertial=q("inertial"); inertial.append(q("mass","0.18")); inertia=q("inertia")
    for k,v in {"ixx":"0.00015","iyy":"0.00015","izz":"0.00015","ixy":"0","ixz":"0","iyz":"0"}.items(): inertia.append(q(k,v))
    inertial.append(inertia); link.append(inertial); root.append(link)
    joint=q("joint",type="prismatic",name="payload_drop_joint"); joint.append(q("parent",base_link)); joint.append(q("child","vanni_payload_drop")); joint.append(q("pose","0 0 -0.12 0 0 0")); axis=q("axis"); axis.append(q("xyz","0 0 1")); lim=q("limit"); lim.append(q("lower","-0.18")); lim.append(q("upper","0")); axis.append(lim); joint.append(axis); root.append(joint)
def add_ardupilot_plugins(root: ET.Element, model_name: str, rotors, imu_name: str):
    for idx,(joint_name,rotor_link) in enumerate(rotors):
        sign=-1 if idx in (2,3) else 1
        lift=q("plugin",name=f"LiftDragRotor{idx}",filename="gz-sim-lift-drag-system")
        for k,v in {"a0":"0.3","alpha_stall":"1.4","cla":"4.25","cda":"0.10","cma":"0.0","cla_stall":"-0.025","cda_stall":"0.0","cma_stall":"0.0","area":"0.002","air_density":"1.2041","cp":"0.084 0 0","forward":f"0 {sign} 0","upward":"0 0 1","link_name":rotor_link}.items(): lift.append(q(k,v))
        root.append(lift); force=q("plugin",name=f"ApplyJointForce{idx}",filename="gz-sim-apply-joint-force-system"); force.append(q("joint_name",joint_name)); root.append(force)
    root.append(q("plugin",name="JointStatePublisher",filename="gz-sim-joint-state-publisher-system"))
    ap=q("plugin",name="ArduPilotPlugin",filename="ArduPilotPlugin")
    for k,v in {"fdm_addr":"127.0.0.1","fdm_port_in":"9002","connectionTimeoutMaxCount":"10","lock_step":"1","no_time_sync":"1","have_32_channels":"0"}.items(): ap.append(q(k,v))
    ap.append(q("modelXYZToAirplaneXForwardZDown","0 0 0 180 0 0",degrees="true")); ap.append(q("gazeboXYZToNED","0 0 0 180 0 90",degrees="true")); ap.append(q("imuName",imu_name))
    for idx,(joint_name,_) in enumerate(rotors):
        c=q("control",channel=str(idx))
        for k,v in {"jointName":joint_name,"useForce":"1","multiplier":str(838 if idx<2 else -838),"offset":"0","servo_min":"1100","servo_max":"1900","type":"VELOCITY","p_gain":"0.20","i_gain":"0","d_gain":"0","i_max":"0","i_min":"0","cmd_max":"2.5","cmd_min":"-2.5","controlVelocitySlowdownSim":"1"}.items(): c.append(q(k,v))
        ap.append(c)
    c=q("control",channel="8")
    for k,v in {"jointName":"payload_drop_joint","useForce":"1","multiplier":"-0.18","offset":"0","servo_min":"1100","servo_max":"1900","type":"POSITION","p_gain":"8.0","i_gain":"0","d_gain":"0","i_max":"0","i_min":"0","cmd_max":"0","cmd_min":"-0.18"}.items(): c.append(q(k,v))
    ap.append(c); root.append(ap)
def main():
    if not SRC.exists(): print(f"Missing source model: {SRC}",file=sys.stderr); return 2
    src_sdf=find_model_sdf(SRC); tree=ET.parse(src_sdf); sdf=tree.getroot(); model=sdf.find("model")
    if model is None: raise RuntimeError(f"No <model> root in {src_sdf}")
    model.set("name","vannikawachh_f450"); model_name="vannikawachh_f450"; clean_plugins(model); normalize_poses(model)
    rotors=get_rotors(model); base_link=get_base_link(model); imu_name=ensure_imu(model,model_name,base_link); add_payload(model,base_link); add_ardupilot_plugins(model,model_name,rotors,imu_name)
    if DST.exists(): shutil.rmtree(DST)
    shutil.copytree(SRC,DST); (DST/"model.sdf").write_text(ET.tostring(sdf,encoding="unicode"),encoding="utf-8")
    (DST/"model.config").write_text("<?xml version='1.0'?>\n<model>\n  <name>vannikawachh_f450</name>\n  <version>1.0</version>\n  <sdf version='1.9'>model.sdf</sdf>\n  <author><name>VanniKawachh</name></author>\n  <description>F450 visual model adapted for ArduPilot SITL + Gazebo Harmonic.</description>\n</model>\n",encoding="utf-8")
    print(f"Prepared: {DST/'model.sdf'}"); print(f"Rotor joints: {[x[0] for x in rotors]}"); print(f"IMU: {imu_name}"); print("Payload actuator: ArduPilot SERVO9 -> payload_drop_joint"); return 0
if __name__=="__main__": raise SystemExit(main())
