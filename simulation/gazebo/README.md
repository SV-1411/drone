# VanniKawachh — ArduPilot + Gazebo Harmonic F450 Simulation

This is the authoritative flight-physics layer for the project.

## What is real here

- Gazebo Harmonic provides the 3D world, gravity, rigid-body dynamics, rotor joints, collision and sensors.
- ArduCopter SITL is the flight controller.
- The official ArduPilot Gazebo plugin maps ArduPilot servo/motor outputs to Gazebo joints and sends simulated sensor state back to SITL.
- Wokwi still triggers the VanniKawachh hub.
- `simulation/sitl_bridge.py` watches the deployed hub for a dispatched incident, commands ArduCopter with MAVLink, and pushes live telemetry back to `/sitl-report`.

ArduPilot's official Gazebo documentation supports Gazebo Harmonic and documents the `gazebo-... --model JSON` Copter SITL workflow. The plugin supports VELOCITY, POSITION, EFFORT and COMMAND control types.

Sources:
- https://ardupilot.org/dev/docs/sitl-with-gazebo.html
- https://github.com/ArduPilot/ardupilot_gazebo

## F450 visual reference

The visual hardware target is the DJI Flamewheel F450. The reference repo `mathieuvenot/F450` contains the actual F450 setup documentation and supporting files. A second open-source repository, `beomsu7/px4-quadrotor-HW-parts`, contains a custom F450 Gazebo visual model and notes how its author replaced the default Iris visual with custom F450 geometry. We use that as the visual source only; the flight-control/physics side is ArduPilot + the current official Gazebo plugin. The VanniKawachh configuration does not claim those repositories are your procurement BOM.

Sources:
- https://github.com/mathieuvenot/F450
- https://github.com/beomsu7/px4-quadrotor-HW-parts

## Windows path

The recommended environment is Ubuntu 22.04 under WSL2 with OpenGL hardware acceleration. Gazebo Harmonic provides official Ubuntu 22.04 binaries, and ArduPilot documents Gazebo Harmonic for SITL.

### 1. Install prerequisites

The one-command setup script performs the package installation and official Gazebo repository configuration:

```bash
./simulation/gazebo/setup_f450_harmonic.sh
```

Gazebo's official Ubuntu instructions install the `gz-harmonic` metapackage from `packages.osrfoundation.org`.

Source: https://gazebosim.org/docs/harmonic/install_ubuntu/

### 2. Install and build ArduPilot

The setup script clones ArduPilot, installs its Ubuntu prerequisites, builds the SITL Copter target, and builds the official ArduPilot Gazebo plugin.

### 3. Prepare the F450 visual model

The setup script clones the open F450 visual source outside the main repository and runs:

```bash
python3 simulation/gazebo/prepare_f450.py
```

The preparation script removes PX4/legacy flight-control plugins from the visual source, discovers its four rotor joints and IMU, injects the current ArduPilot Gazebo plugin, and adds a simulated SERVO9-controlled health-kit drop mechanism.

### 4. Launch the real simulation

One-shot launch:

```bash
./simulation/gazebo/run_vannikawachh.sh all
```

Or run the layers separately:

```bash
./simulation/gazebo/run_vannikawachh.sh gazebo
./simulation/gazebo/run_vannikawachh.sh sitl
./simulation/gazebo/run_vannikawachh.sh bridge
```

The bridge uses:

```text
VANNIKAWACHH_HUB=https://vannikawachh-hub.onrender.com
MAVLINK_CONNECTION=udp:127.0.0.1:14550
```

### 5. Mission flow

1. Press `SCREAM` in Wokwi.
2. The ESP32 calls `/node-alert`.
3. The hub creates a dispatched mission with the distress GPS.
4. The local SITL bridge detects the new incident from `/incidents`.
5. ArduCopter switches to GUIDED and arms.
6. `NAV_TAKEOFF` climbs from the Gazebo launch surface to 15 m AGL.
7. A MAVLink global-position target sends the aircraft to the distress GPS.
8. The vehicle hovers for the configured dwell time.
9. A MAVLink `MAV_CMD_DO_SET_SERVO` command moves the simulated payload-drop actuator.
10. RTL returns the vehicle to home and ArduPilot lands/disarms it.
11. The bridge continuously reports live telemetry to Render through `/sitl-report`.
12. When SITL telemetry is fresh, the deployed `/drone_state` feed is served from that real simulation state, so the existing GCS/hardware pages can observe the live aircraft.

## Important distinction

The Render browser simulator remains as a deterministic fallback. It is not the physics validation layer. **Gazebo + ArduPilot SITL is the authoritative flight-physics simulator.**

## Safety

This is a software simulation. Before connecting any real Pixhawk or motors, keep propulsion disconnected, verify all ArduPilot safety/pre-arm behavior, and follow the aircraft manufacturer's and ArduPilot's setup/calibration procedures.
