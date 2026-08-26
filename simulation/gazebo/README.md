# VanniKawachh — ArduPilot + Gazebo Harmonic F450 Simulation

This is the authoritative flight-physics layer for the project.

## What is real here

- Gazebo Harmonic provides the 3D world, gravity, rigid-body dynamics, rotor joints, collision and sensors.
- ArduCopter SITL is the flight controller.
- The official ArduPilot Gazebo plugin maps ArduPilot servo/motor outputs to Gazebo joints and sends simulated sensor state back to SITL.
- Wokwi still triggers the VanniKawachh hub.
- `simulation/sitl_bridge.py` watches the deployed hub for a dispatched incident, commands ArduCopter with MAVLink, and pushes live telemetry back to `/sitl-report`.

ArduPilot officially supports Gazebo Harmonic (recommended) and documents the `gazebo-... --model JSON` workflow for Copter SITL. The current official plugin also supports VELOCITY, POSITION, EFFORT and COMMAND control types. citehttps://ardupilot.org/dev/docs/sitl-with-gazebo.html

## F450 visual reference

The visual hardware target is the DJI Flamewheel F450. The reference repo `mathieuvenot/F450` contains the actual F450 setup documentation and supporting files. A second open-source repository, `beomsu7/px4-quadrotor-HW-parts`, contains a custom F450 Gazebo visual model and notes how its author replaced the default Iris visual with custom F450 geometry. We use that as the visual source only; the flight-control/physics side is ArduPilot + the current official Gazebo plugin. The VanniKawachh configuration does not claim those repositories are your procurement BOM. citehttps://github.com/mathieuvenot/F450 citehttps://github.com/beomsu7/px4-quadrotor-HW-parts

## Windows path

The recommended environment is Ubuntu 22.04 under WSL2 with OpenGL hardware acceleration. ArduPilot's current Gazebo documentation supports Ubuntu 22.04 and recommends Gazebo Harmonic. citehttps://github.com/ArduPilot/ardupilot_gazebo/blob/main/README.md

### 1. Install prerequisites

```bash
sudo apt update
sudo apt install -y git curl wget python3 python3-pip python3-venv build-essential cmake rapidjson-dev libopencv-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-gl
```

Install Gazebo Harmonic using the official Gazebo package instructions for Ubuntu 22.04, then verify:

```bash
gz sim -v4 -r shapes.sdf
```

### 2. Install ArduPilot

From your home directory:

```bash
cd ~
git clone https://github.com/ArduPilot/ardupilot.git --depth 1
cd ardupilot
Tools/environment_install/install-prereqs-ubuntu.sh -y
. ~/.profile
./waf configure --board sitl
./waf copter
```

### 3. Install the official Gazebo plugin

```bash
cd ~
git clone https://github.com/ArduPilot/ardupilot_gazebo.git --depth 1
cd ardupilot_gazebo
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j"$(nproc)"
```

Then add the resource/plugin paths to `~/.bashrc`:

```bash
export GZ_VERSION=harmonic
export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH}
export GZ_SIM_RESOURCE_PATH=$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:${GZ_SIM_RESOURCE_PATH}
```

Reload:

```bash
source ~/.bashrc
```

These environment variables and the Harmonic build flow are from the official ArduPilot Gazebo project. citehttps://github.com/ArduPilot/ardupilot_gazebo/blob/main/README.md

### 4. Get the F450 visual source

From the VanniKawachh repository root:

```bash
mkdir -p third_party
cd third_party
git clone https://github.com/beomsu7/px4-quadrotor-HW-parts.git
cd ..
python3 simulation/gazebo/prepare_f450.py
```

The preparation script removes PX4-specific MAVLink plugins from the imported visual model, discovers its rotor joints/IMU, adds the official ArduPilot plugin and adds a simulated servo-driven payload drop joint.

### 5. Launch the real simulation

Terminal A — Gazebo Harmonic:

```bash
cd ~/YOUR_REPO_PATH
./simulation/gazebo/run_vannikawachh.sh gazebo
```

Terminal B — ArduCopter SITL:

```bash
cd ~/YOUR_REPO_PATH
./simulation/gazebo/run_vannikawachh.sh sitl
```

Terminal C — VanniKawachh bridge:

```bash
cd ~/YOUR_REPO_PATH
python3 -m venv .venv-sitl
source .venv-sitl/bin/activate
pip install -r simulation/requirements-sitl.txt
VANNIKAWACHH_HUB=https://vannikawachh-hub.onrender.com MAVLINK_CONNECTION=udp:127.0.0.1:14550 python simulation/sitl_bridge.py
```

For a one-shot run, the launcher can start all three processes if the dependencies are already installed:

```bash
./simulation/gazebo/run_vannikawachh.sh all
```

## Mission flow

1. Press `SCREAM` in Wokwi.
2. The ESP32 calls `/node-alert`.
3. The hub creates a dispatched mission with the distress GPS.
4. The local SITL bridge detects the mission from `/incidents`.
5. ArduCopter switches to GUIDED and arms.
6. `NAV_TAKEOFF` climbs from the Gazebo launch surface to 15 m AGL.
7. A MAVLink global-position target sends the vehicle to the incident GPS.
8. The vehicle hovers for the configured dwell time.
9. A MAVLink `MAV_CMD_DO_SET_SERVO` command moves the simulated payload-drop actuator.
10. RTL sends the vehicle back to the launch point and ArduPilot lands/disarms.
11. The bridge continuously reports telemetry to Render through `/sitl-report`.
12. `/drone_state_live` becomes the live source for a GCS page whenever SITL telemetry is fresh; otherwise the deployed browser simulator remains available.

## Important distinction

The Render browser simulator is a presentation fallback. Gazebo + ArduPilot is the actual flight-physics simulator. Do not describe the browser fallback as aerodynamic validation.

## Safety

This is a software simulation. Before connecting any real Pixhawk or motors, keep propulsion disconnected, verify all ArduPilot safety/pre-arm behavior, and follow the aircraft manufacturer's and ArduPilot's setup/calibration procedures.
