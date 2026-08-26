# VanniKawachh — Real Flight-Physics Simulation

## Why this exists

The deployed Render pages are the presentation/mission layer. They do not emulate aerodynamic lift, rigid-body dynamics, ESC/motor thrust, IMU drift, or ArduPilot control loops.

For that, use the official ArduPilot SITL + Gazebo integration.

Official ArduPilot documentation currently supports Gazebo Garden and Gazebo Harmonic. The official `ardupilot_gazebo` project provides an Iris quadcopter model and a working `ArduCopter` SITL configuration.

## Target architecture

```text
Wokwi ESP32
    |
    | GET /node-alert
    v
VanniKawachh Hub (Render)
    |
    | mission appears in /drone_state
    v
simulation/sitl_bridge.py
    |
    | MAVLink
    v
ArduPilot SITL (ArduCopter)
    |
    | JSON/SITL interface
    v
Gazebo Harmonic
    |
    +-- rigid body
    +-- gravity
    +-- motor/propeller forces
    +-- IMU
    +-- GPS
    +-- barometer
    +-- camera (optional)
```

## Official baseline

ArduPilot's current Gazebo instructions use:

```bash
gz sim -v4 -r iris_runway.sdf
sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --map --console
```

Then the documented basic sequence is:

```text
GUIDED
arm throttle
takeoff 5
```

The official Gazebo plugin is `ArduPilot/ardupilot_gazebo`.

## VanniKawachh mission sequence

The bridge watches the deployed hub for a new mission and commands SITL through MAVLink:

```text
IDLE
  -> ARMING
  -> TAKEOFF
  -> ENROUTE
  -> HOVERING
  -> DELIVERING
  -> RTL
  -> LANDING
  -> COMPLETED
```

The mission target is the GPS coordinate supplied by Wokwi through `/node-alert`.

## Important deployment boundary

The current Render free service should remain the web/API layer. Render's free instances do not provide free private/background-worker service types, so the full Gazebo GUI + ArduPilot SITL stack is not placed inside the existing free web service.

This is deliberate. The browser page is a visualization; Gazebo is the physics engine. A funding presentation can show both side-by-side, while the deployed web page remains available to demonstrate the trigger and mission API.

## Acceptance criteria

1. Wokwi `SCREAM` calls `/node-alert`.
2. The hub creates a mission with the Wokwi GPS coordinate.
3. The bridge detects the new mission.
4. ArduCopter SITL arms only after GPS/vehicle readiness.
5. Gazebo shows the vehicle on the launch surface.
6. The aircraft lifts vertically to cruise altitude rather than translating immediately.
7. The aircraft cruises to the target using the autopilot/Gazebo physics.
8. The vehicle stops and hovers over the target.
9. The payload release command is issued through a simulated servo output.
10. RTL is commanded and the aircraft returns to launch.
11. The vehicle descends and lands.

The web viewer should never be described as the physics validation layer unless a live SITL source is connected.
