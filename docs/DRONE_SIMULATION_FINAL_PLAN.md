# VanniKawachh — Final Drone Simulation Architecture

## 1. Objective

The demo must show two different things without conflating them:

1. **Geographic flight simulation** — the aircraft starts on a launch/landing pad, arms, spins four rotors, climbs vertically, cruises to the distress GPS coordinate, hovers, releases the health kit, returns to the launch point and lands.
2. **Physical hardware architecture** — a real-looking quadcopter/frame with the proposed onboard components and correctly explained power, sensor, telemetry and actuator connections.

The Wokwi ESP32 remains the trigger source. The existing `/node-alert` and `/drone_state` APIs remain the single integration path for the deployed web demo.

## 2. Final system boundary

```text
Wokwi ESP32 sensor node
    -> HTTPS /node-alert
    -> VanniKawachh hub / dispatch
    -> mission state /drone_state
    -> browser visualisation

For real flight-control validation:
Wokwi/hub mission
    -> MAVLink mission adapter
    -> ArduPilot SITL
    -> Gazebo Harmonic
    -> simulated vehicle/sensors/actuators
```

The browser UI is not presented as aerodynamic physics. ArduPilot SITL + Gazebo is the physics-validation layer.

## 3. Aircraft hardware architecture

### Power path

```text
LiPo battery
  -> fuse / power distribution board / power module
  -> ESC 1 -> BLDC motor 1 -> propeller 1
  -> ESC 2 -> BLDC motor 2 -> propeller 2
  -> ESC 3 -> BLDC motor 3 -> propeller 3
  -> ESC 4 -> BLDC motor 4 -> propeller 4
```

Pixhawk is powered through its dedicated power input/power module. ESC signal + signal ground connect to the autopilot outputs. A PDB can distribute motor power while the autopilot receives the signal connections. This follows ArduPilot's published Pixhawk/ESC wiring guidance.

### Flight-control path

```text
GPS + compass + IMU
        -> Pixhawk / ArduPilot
        -> motor outputs 1..4
        -> ESC control
        -> motor thrust
```

For an X quad, two motors rotate CW and two rotate CCW according to the configured motor-order diagram. Exact motor numbering must match the chosen frame and ArduPilot motor-test output assignment.

### Mission communications

```text
ESP32 sensing node
      -> hub / LoRa gateway
      -> companion computer / mission interface
      -> Pixhawk MAVLink/telemetry link
```

The ESP32 is not a direct motor controller. Pixhawk/ArduPilot is responsible for flight stabilization and motor output.

### Payload

```text
Pixhawk/companion
    -> servo output
    -> payload-bay latch
    -> health-kit release
```

The payload channel must be explicitly mapped and shown on the hardware page.

## 4. Browser routes — no more route proliferation

### `/drone-sim`

High-level end-to-end mission presentation only. It should never contain the detailed hardware CAD/circuit view.

### `/drone-flight`

Geographic flight view only. This shows launch pad, 3D world, route, live aircraft GPS, altitude, speed, heading, ETA, takeoff/climb, cruise, hover, payload action, RTL and landing.

### `/drone-hardware`

Wokwi-equivalent engineering view. This shows the aircraft model and the physical wiring architecture: battery/PDB, Pixhawk, GPS/compass/IMU, companion/LoRa, four ESCs, four motors/props, camera and payload servo. It must react to the same live mission state and provide explicit success/error feedback for every button.

`/drone-physical` remains only a compatibility alias and is not a new implementation.

## 5. Simulation phases

The mission state machine is:

```text
IDLE
 -> ARMING
 -> TAKEOFF / VERTICAL CLIMB
 -> ENROUTE
 -> HOVERING
 -> DELIVERING
 -> RTL
 -> LANDING / VERTICAL DESCENT
 -> COMPLETED
```

The physical-browser simulation uses geographic distance divided by configured cruise speed. No fixed 1-second animation and no hidden 10x/600x acceleration are permitted.

## 6. Actual physics implementation

ArduPilot's current official documentation supports Gazebo Garden and Gazebo Harmonic for Copter SITL and provides an Iris quadcopter example. The recommended real-physics path is ArduPilot SITL + the official `ardupilot_gazebo` plugin + Gazebo Harmonic.

Gazebo is not appropriate to run inside the existing free Render web service itself. Render's free tier supports free web services/static sites but not free background-worker/private-service instances. Therefore:

- Render hosts the VanniKawachh web UI and mission API.
- ArduPilot SITL + Gazebo runs in a dedicated simulation environment (developer workstation or paid simulation host).
- A MAVLink/WebSocket bridge connects the two.

This separation is deliberate and must be documented instead of pretending a browser animation is Pixhawk physics.

## 7. Model strategy

Use a real 3D quadcopter/CAD-style aircraft shell rather than procedural boxes. The supplied Sketchfab `inside-drone` model is a candidate for the hardware presentation if its license permits the intended use. The page will use an embeddable high-fidelity viewer/model and separate annotated engineering connection graphics for Pixhawk, battery, ESCs, motors and payload.

For the actual Gazebo model, use an ArduPilot-supported quad model and only replace the visual mesh once the flight dynamics and motor mapping have been validated. A detailed rendered shell must never silently change the physics model.

## 8. Acceptance tests

### Integration

- Trigger from Wokwi `/node-alert` changes mission from IDLE to ARMING.
- `/drone_state` becomes live and remains readable during the entire mission.
- Buttons show a visible pending/success/error status and HTTP response.

### Flight

- Aircraft visibly starts on the launch surface.
- Rotor spool/arming happens before movement.
- Aircraft climbs vertically to cruise altitude.
- Cruise time is proportional to geographic distance / configured speed.
- Aircraft reaches target, stops horizontally and hovers.
- Payload actuator changes state, then kit is released.
- Aircraft returns at cruise altitude.
- Aircraft descends vertically to the launch surface.
- Final state is COMPLETED and aircraft is physically on the pad.

### Hardware

- Pixhawk, GPS/compass/IMU, PDB/power module, four ESCs, four motors, propellers, companion/telemetry, camera and payload servo are visible.
- Power and control/data paths are visually distinct.
- Motor directions match the configured X-frame order.
- Hardware screen has no geographic globe.

## 9. Current repo issues to fix before adding features

- `/drone-hardware` has a browser JavaScript redeclaration error (`frame` collision) in the current implementation.
- `/drone-sim` is currently coupled to the geographic viewer and inherits its event-listener failure.
- The current live-hub control path does not provide robust connection/error feedback.
- The current hardware visual is too procedural/block-like for presentation and needs a high-fidelity aircraft model.

These are prerequisites, not optional polish.
