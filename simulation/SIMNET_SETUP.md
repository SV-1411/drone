# VanniKawachh + SIMNET / ArduPilot Integration

## Why SIMNET

SIMNET is the high-fidelity flight layer. Its public documentation describes a physics engine with multicopter components including propellers, brushless motors, ESCs, LiPo batteries, flight controllers, mixers, servos and payloads; it also provides 6-DOF flight simulation and ArduPilot/PX4 SITL integration. It provides worldwide 3D terrain and a real-time state pane.

## Reference aircraft

Use the SIMNET F450/ArduPilot aircraft as the baseline. The open PRIAM F450 project used as our hardware reference contains:

- Flamewheel F450 frame
- DJI 2312E 960KV motors (x4)
- DJI 9450 props
- APD 80A ESCs (x4)
- Pixhawk 2.1 CubeOrange
- Drotek F9P RTK GPS
- 915 MHz SiK telemetry
- 4S 4500 mAh LiPo

Do not present these as the final procurement BOM until the college hardware is confirmed.

## SIMNET setup

1. Create/sign in to a SIMNET account.
2. Load an ArduPilot-enabled quadcopter aircraft (the SIMNET SITL tutorial explains that aircraft names containing `ArduPilot` or `PX4` are prepared for SITL).
3. Create or load the desired geographic location and select the safe takeoff pad.
4. Open SIMNET's **Ground Control Station** panel. SIMNET exposes a TCP IP/port for the current SITL session.
5. The VanniKawachh Render service accepts those values through:
   - `SIMNET_HOST`
   - `SIMNET_PORT`
6. Optional payload settings:
   - `SIMNET_PAYLOAD_SERVO` (default 9)
   - `SIMNET_PAYLOAD_PWM` (default 1900)
   - `SIMNET_TAKEOFF_ALT_M` (default 15)
7. Redeploy the Render service after setting the variables.

## Mission flow

The existing Wokwi ESP32 still calls `/node-alert`. When the SIMNET endpoint is configured, the hub's existing dispatch path uses MAVLink to:

`DISTRESS -> GUIDED -> ARM -> TAKEOFF -> GOTO TARGET -> HOVER -> PAYLOAD SERVO -> RTL`

Telemetry is read from MAVLink and exposed through the existing `/drone_state` endpoint so the VanniKawachh dashboard and hardware view consume the same mission source.

## Important limitation

SIMNET's public documentation does not provide a public browser-embed/session-control API that can be safely assumed from a Render webpage. The supported integration documented by SIMNET is a session-specific GCS TCP connection. Therefore the Render server does not guess a session endpoint; it activates the real MAVLink backend only when `SIMNET_HOST` and `SIMNET_PORT` are explicitly configured.

## Demo acceptance criteria

- The aircraft starts on the selected takeoff pad.
- Motors/rotors spool before vertical movement.
- Takeoff is visible as a real climb from ground level.
- The aircraft flies using ArduPilot's SITL/physics model rather than a linear browser animation.
- GPS position, altitude and speed change continuously.
- The vehicle reaches the incident location and hovers.
- A servo command is sent for the health-kit release.
- RTL is commanded and the aircraft returns and lands.
- `/drone_state` reports the same live telemetry seen in the simulation.
