# VanniKawachh -- Tinkercad hardware simulation (seed-money demo)

A working circuit demo you build in the browser: a **Sensor Node** detects
distress and raises an alert; the **Drone** arms its 4 rotor motors, flies,
drops the first-aid kit with a servo, and returns. Optional third board (the
**Hub**) adds the two-stage verification.

Tinkercad has no file import, so this folder gives you the **Arduino code +
exact wiring**; you drag the parts onto the canvas and paste the sketches.

## Read this to your reviewers (the honest, correct claim)

A circuit simulator proves the **electronics and firmware**: the sensors, the
detection logic, the alert link, the motor arming/throttle, the kit-drop servo,
the camera trigger. That is real and it is what "if it simulates, the hardware
works" means.

Two things no circuit simulator can do, and how we prove them instead:
* **A real scream into a real mic + the CNN** -> represented here by the knob
  (loudness) and the red button (scream); the AI is proven with **Edge Impulse**
  (runs the model on the ESP32-S3) and the working software pipeline.
* **The quadcopter actually flying** (BLDC + ESC + Pixhawk aerodynamics) ->
  proven in a **flight simulator, ArduPilot SITL / Gazebo**, which this project
  already runs. In Tinkercad the "flight" is the 4 motors spinning + the mission
  sequence; the real flight path is the SITL demo.

This split (circuits in a circuit sim, flight in a flight sim) is exactly how
real drone companies validate hardware. Together they cover the whole system.

## Before you start

Go to https://www.tinkercad.com (free Autodesk account) -> **Circuits** ->
**Create new Circuit**. You can put **all boards in ONE circuit** so they talk
to each other.

---

## Board 1 -- SENSOR NODE

**Parts (drag from the components panel):**
Arduino Uno R3, small breadboard, Potentiometer, PIR sensor, Photoresistor,
1x 10k resistor (for the LDR), 3x LED (green, red, blue), 3x 220 ohm resistor,
Piezo (buzzer), Pushbutton.

**Wiring:**
| From (Uno) | To | Notes |
|---|---|---|
| A0 | Potentiometer wiper (middle pin) | mic loudness; sides to 5V and GND |
| A1 | Photoresistor + 10k divider | other LDR leg to 5V, junction to A1, 10k to GND |
| D2 | PIR "SIG" | PIR VCC->5V, GND->GND |
| D3 | Pushbutton | other side of button to GND (uses internal pull-up) |
| D4 | green LED (+ 220 ohm to GND) | listening |
| D5 | red LED (+ 220 ohm) | distress |
| D6 | blue LED (+ 220 ohm) | LoRa transmit |
| D7 | Piezo (+), other leg GND | buzzer |
| D8 | **alert line -> goes to the Drone's D2** | the LoRa uplink |

Paste **`node.ino`**.

## Board 2 -- DRONE

**Parts:** Arduino Uno R3, breadboard, **4x DC Motor (Hobby)**, 1x NPN power
transistor (**TIP120**), 1x 1k resistor, 4x diode (1N4001) [flyback],
1x micro Servo, 3x LED (green idle, red busy, white "camera"), 3x 220 ohm,
Piezo. (Optional: a 9V battery / power supply for the motors.)

**4-motor driver (this is the "rotors"):**
| From | To |
|---|---|
| D6 (PWM throttle) | 1k resistor -> TIP120 **Base** |
| TIP120 **Emitter** | GND |
| TIP120 **Collector** | one terminal of all 4 motors (joined) |
| Motors' other terminal (joined) | +5V (or battery +) |
| Diode across each motor | cathode to +5V side, anode to collector side |

Tip: wire ONE motor first, confirm it spins, then add the other three in
parallel. Throttle is on **D6** on purpose: the Servo library disables PWM on
pins 9 & 10, so the motors must use a Timer0 PWM pin (D6).

**Rest of the drone:**
| From (Uno) | To | Notes |
|---|---|---|
| D10 | Servo signal | kit release; servo +->5V, ->GND |
| D4 | white LED (+220 ohm) | camera recording |
| D12 | green LED (+220 ohm) | idle at base |
| D13 | red LED (+220 ohm) | on a mission |
| D8 | Piezo | buzzer |
| D2 | **alert line from the Node's D8** | trigger |

Paste **`drone.ino`**.

## The link between the two boards (do not skip)

* Node **D8 -> Drone D2** (the alert / LoRa line).
* **Node GND -> Drone GND** (a shared ground is required, or the signal is
  meaningless).

---

## Run and demo

1. Click **Start Simulation**.
2. The node's green LED is on (listening); the drone's green LED is on (idle).
3. **Trigger distress:** press the red **button**, or drag the **potentiometer**
   past the middle.
4. Watch:
   * node: red LED + buzzer, blue LED blinks (transmitting), alert line HIGH;
   * drone: red "busy" LED + camera LED on, **all 4 motors spin up**, buzzer,
     then the **servo swings to drop the kit**, then motors spin down and it
     returns to idle.
5. Open the **Serial Monitor** (Code -> Serial Monitor) to see the alert packet
   (node id, GPS, confidence) and the drone's mission log.

## Optional -- add the HUB (full two-stage chain)

Add a third Uno with `hub_optional.ino` and rewire the link:
`node D8 -> hub D2` and `hub D8 -> drone D2` (all three share GND). Now the node
alert goes to the hub, the hub "runs Stage-2 verification" (yellow LED blinks),
and only then dispatches the drone (green LED). This shows the node + hub +
drone architecture end to end.

## How each simulated part maps to the real hardware

| In Tinkercad | Real component |
|---|---|
| Potentiometer | INMP441 I2S MEMS microphone |
| Red button | a detected scream (the ESP32 CNN's output) |
| PIR / Photoresistor | PIR motion + light sensor (same parts) |
| Alert line (D8->D2) | SX1278 LoRa 433 MHz uplink |
| Node Uno | ESP32-S3 sensing node |
| Hub Uno | Raspberry Pi 5 running PANNs (Stage-2) |
| 4 DC motors + TIP120 | 4 BLDC motors + ESCs (flight = ArduPilot SITL) |
| Drone Uno | Pixhawk flight controller |
| Servo | first-aid kit release mechanism |
| White LED | onboard camera |

## The complete evidence set for the pitch

1. **This Tinkercad circuit** -- the electronics work (sense -> alert -> drone
   arms -> kit drop).
2. **ArduPilot SITL demo** (`python -m hub.main`) -- the drone actually flies to
   the coordinates on a live map.
3. **Edge Impulse** -- the CNN runs on the ESP32-S3 (latency / RAM / accuracy).
4. **BOM + cost sheet** -- what the seed money buys.
