# VanniKawachh -- hardware simulation (for the seed-money demo)

This folder is the **virtual hardware** proof: a working circuit + firmware you
can run in a browser, so reviewers see the electronics behave before a single
part is bought. It complements the software proof (the hub + dashboard + SITL
drone demo) and the AI-on-chip proof (Edge Impulse).

## What a circuit simulator can and cannot prove (read this first)

A simulator proves **wiring, signals, timing, and firmware logic**. That is the
"if it simulates, the hardware will work" part, and it is real.

No circuit simulator (Wokwi, PCBX, Tinkercad, Proteus) can put a **real scream
into a real microphone** or run a **CNN on live audio** -- there is no audio
input in these tools. So in this simulation:

* the **potentiometer** stands in for microphone loudness, and
* the **red button** stands in for "a scream happened".

Everything *after* that point is the **real logic** running on the **real MCU**:
the detection thresholds, the day/night + motion fusion, the alert packet with
the pole's GPS coordinates, the dispatch decision, and the drone response with
the kit drop. The AI model itself is validated the correct way -- with Edge
Impulse (it deploys the CNN to the ESP32-S3 and reports latency/RAM/accuracy)
and with the software pipeline that already runs the real model on real audio.

Say this plainly to your committee. It is the honest and defensible claim, and
it is stronger than pretending one tool simulates a neural network.

## Why Wokwi (and not PCBX/Tinkercad/Proteus)

* Free, browser-based, nothing to install, and it gives a **shareable link** you
  can paste into the pitch.
* It simulates the **ESP32 family you actually use** (Tinkercad is Arduino-Uno
  only; PCBX is niche; Proteus is paid and weak on ESP32).
* It runs your **real firmware**.

The components and wiring are identical in any of those tools, so if your
professor wants it rebuilt in PCBX/Proteus, this wiring table ports over 1:1.

## Run it (2 minutes)

1. Go to https://wokwi.com and click **New Project -> ESP32**.
2. Open the `diagram.json` tab, select all, and paste the contents of
   `vannikawachh-node/diagram.json`.
3. Open `sketch.ino`, paste the contents of `vannikawachh-node/sketch.ino`.
4. Click the green **Play**. Open the Serial Monitor (bottom).
5. **Demo it:** turn the potentiometer up past the middle, or press the red
   **SCREAM** button. Watch the OLED go
   `Listening -> DISTRESS DETECTED -> Dispatch: GHRCE (ETA) -> Drone en route
   -> KIT DELIVERED`, the LEDs change, the buzzer chirp, the servo drop the
   kit, and the alert packet (node id + GPS + confidence) print on Serial.

To save the shareable link: in Wokwi press **Save** (needs a free account), then
**Share** -> copy the link into your slides.

## Wiring table (source of truth -- fix a wire in seconds if needed)

| Component | Represents | ESP32 pin |
|---|---|---|
| Potentiometer (SIG) | INMP441 mic loudness | GPIO34 (ADC) |
| Photoresistor (AO) | ambient light / day-night | GPIO35 (ADC) |
| PIR motion (OUT) | someone present | GPIO27 |
| Pushbutton "SCREAM" | a scream event | GPIO14 (+ GND) |
| OLED SSD1306 SDA / SCL | status display | GPIO21 / GPIO22 |
| Servo (PWM) | first-aid kit release | GPIO13 |
| Green LED | idle / listening | GPIO2 |
| Red LED | distress confirmed | GPIO4 |
| Blue LED | LoRa packet transmit | GPIO5 |
| Buzzer | siren cue | GPIO18 |

Power: sensors + OLED to 3V3, PIR + servo to 5V, all grounds to GND.

Real hardware note: add a 220 ohm resistor in series with each LED (the sim
tolerates a direct connection; a real LED needs it).

## What this maps to in the real product

* This board = the **roadside sensing node** (ESP32-S3 + INMP441 + PIR + LDR +
  NEO-6M GPS + SX1278 LoRa). In the sim, the LoRa uplink is shown as the blue
  LED + the packet printed on Serial (RF cannot be simulated).
* The **hub** (Raspberry Pi 5 + PANNs) and the **drone** (Pixhawk + ArduPilot)
  are separate units -- already proven in software and SITL. Here their roles
  (dispatch decision + flight + kit drop) are shown compressed on the one board
  so the full story is visible in a single view.

## The full evidence set for the pitch

1. **This Wokwi sim** -- the electronics + node firmware work.
2. **Software demo** (`python -m hub.main --web-only`) -- real detection ->
   dispatch -> drone flight on the live map.
3. **Edge Impulse** -- the CNN runs on the ESP32-S3 (latency/RAM/accuracy).
4. **BOM + cost sheet** -- what the seed money buys.
