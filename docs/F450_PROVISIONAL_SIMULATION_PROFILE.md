# F450 1000 KV + 3S 2200 mAh — provisional SITL/Gazebo profile

## Status and safety boundary

This is a **simulation-planning profile**, not a physical-aircraft parameter
file. It is based on the hardware information currently available:

| Component | Known information | Simulation treatment |
|---|---|---|
| Frame | Red F450-style, 450 mm quad | Quad-X geometry |
| Motors | Four **A2212/13T 1000 KV** motors | A2212-class 1000 KV placeholder; prop data still unknown |
| ESCs | Four **SimonK 30 A** ESCs | Generic PWM multirotor ESC placeholder; 30 A is the applicable limit |
| Battery | Bonka 3S 2200 mAh 35C | 11.1 V nominal, 24.4 Wh planning budget; weigh the actual pack before final calibration |
| Pixhawk | 2.4.8 | ArduCopter SITL autopilot |
| GPS | **M8N GPS + compass** | GPS-equipped Quad-X; mount the real compass away from power wiring |
| Radio | FlySky FS-i6 | Pilot radio/receiver check; transmitter is not aircraft mass |
| Props | Unknown | **Assume 1045 only for provisional runs** |

No physical Pixhawk must receive `ARMING_CHECK 0`; it exists in the SITL
profile only. Real hardware must retain pre-arm checks, calibrated battery
monitoring and enabled radio/battery/GPS failsafes.

## Mass cases to test

The model should be exercised at both values, rather than pretending that the
electronics mass is free.

| Case | Target mass | What it represents |
|---|---:|---|
| Base | 1.15 kg | Frame, landing gear, motors, ESCs, props, battery, Pixhawk, GPS, receiver, PDB/power module and wiring |
| Loaded | 1.30 kg | Base aircraft plus companion computer/regulator, ESP32, LoRa/antenna and mounts |

These are planning values. Replace them with a scale measurement of the fully
assembled aircraft before interpreting flight time, throttle or thrust results.

The current Gazebo F450 asset is a visual/rigid-body approximation and is not
yet a measured digital twin. Its rotor plugin provides a stable SITL physics
aircraft; it does **not** contain a manufacturer thrust curve for your exact
motor, propeller and battery. The two masses above are the required planning
envelope, not a fabricated precision result.

## Provisional propulsion envelope

Only if the motors are A2212-class 1000 KV units and the props are healthy
1045 CW/CCW props on the 3S pack, model static peak thrust as **0.8–1.0 kg per
motor**. That gives a planning total of 3.2–4.0 kg static thrust and an
estimated thrust-to-weight ratio of 2.5–3.5 at the two mass cases above.

This is not a substitute for a thrust-stand test. A different motor size,
propeller, worn battery, wrong prop direction, damaged prop or poor solder
joint invalidates the estimate.

## Simulation mission profile

The existing browser demo is not the flight-physics authority. Use ArduPilot
SITL + Gazebo Harmonic and this conservative profile:

```text
frame             Quad X
mission altitude  10 m AGL
cruise speed       2.5 m/s
acceleration       1.0 m/s²
landing speed      0.3 m/s
RTL altitude       10 m
```

Start it on the Gazebo/ArduPilot Linux host with:

```bash
export F450_PARAM_FILE="$PWD/simulation/gazebo/arducopter-f450-a2212-3s2200-provisional.parm"
export DRONE_CRUISE_ALT_M=10
./simulation/gazebo/run_vannikawachh.sh all
```

The Gazebo model must also be updated with measured inertial mass and
motor/prop thrust data once the outstanding parts are identified.

## Required test order

1. SITL: arm → takeoff → hold → waypoint → RTL → land.
2. SITL: reject invalid target, GPS/EKF readiness failure, companion link
   failure, RC loss and low-battery scenarios.
3. Physical bench, **all props removed**: Pixhawk power, radio, GPS, compass,
   accelerometer, battery monitor and motor-test mapping.
4. Props installed only after motor order and CW/CCW rotation are proven.
5. First outdoor flight is a brief manual Stabilize hover with no Pi, ESP32,
   LoRa or autonomous mission.
6. Verify Loiter, then RTL, then add the companion payload, then test guided
   missions. Automatic dispatch is last.

## Do not assemble/flight-gate without these confirmations

- Propeller marking and a matched 2×CW / 2×CCW set.
- Actual propeller diameter/pitch (for example, 1045) and the exact prop
  hub/adaptor used by the A2212 motors.
- Exact GPS/compass model and physical mounting location.
- Exact FlySky receiver model and its Pixhawk-compatible RC connection path.
- Pixhawk-compatible power module / correctly rated PDB.
- Separate 5 V regulator for any Raspberry Pi; never power the Pi from a
  Pixhawk telemetry/USB rail.
- Battery voltage/current monitor calibration and verified low/critical
  actions for this 3S pack.
- Measured final aircraft mass and centre of gravity.

## Mechanical recommendation

Use normal landing gear for initial flight testing. Foam/sponge balls may help
with a gentle cosmetic bump but are not a landing gear substitute: they can
shift the centre of gravity, snag grass, compress unevenly and offer no
clearance for the battery/prop wash. Test the base airframe first; do not put
the Pi 5 and ESP32 on the first flight.
