# Drone ESP to Pixhawk handoff — 21 October 2026

## What this change is for

This is the drone-mounted ESP32-S3 bridge. It is not the microphone sensing
node. Its job is:

1. Poll the private VanniKawachh cloud queue for a server-verified incident.
2. Read Pixhawk MAVLink telemetry through TELEM2.
3. Upload a three-item Pixhawk mission: takeoff, destination waypoint, and
   return-to-launch.
4. Report mission upload and telemetry status back to the cloud.

The ESP bridge does **not** arm the vehicle or start AUTO mode. A successful
`MISSION_ACK` only means Pixhawk accepted the mission. This is deliberate for
the first physical connection check.

## Final wiring

Power **off** the ESP and Pixhawk before wiring.

| Pixhawk TELEM2 | ESP32-S3 7Semi |
|---|---|
| Pin 2, TX | GPIO18 |
| Pin 3, RX | GPIO17 |
| Pin 6, GND | GND |

Do not use the ESP header pins printed `TX` and `RX`; those are GPIO43/GPIO44
and share the board's USB-to-UART hardware. Leave TELEM2 pin 1 (5 V), pin 4
(CTS), and pin 5 (RTS) unconnected. Leave the previously attached separate
5 V wire disconnected for the test. Power Pixhawk normally and power the ESP
through its USB cable.

## Firmware state

`firmware/drone_esp_uart_probe/drone_esp_uart_probe.ino`

* Receive-only hardware test.
* Listens only on GPIO18 at 57,600 baud.
* Never transmits to Pixhawk, never arms, and never sends a mission.
* Prints valid MAVLink heartbeat information at 115,200 baud over USB.

`firmware/drone_esp/drone_esp.ino`

* Complete cloud queue and MAVLink mission-upload bridge.
* Uses GPIO18 as RX and GPIO17 as TX at 57,600 baud.
* Requires a fresh ArduPilot heartbeat, fresh GPS/position, 3D GPS fix,
  at least six satellites, a disarmed Pixhawk, and a target within 30 m before
  attempting mission upload.
* Uses a 32 KiB UART receive buffer so short cloud HTTP delays do not discard
  Pixhawk telemetry.
* Does not arm or start the mission.

The saved Pixhawk parameters used by this firmware are `SERIAL2_PROTOCOL=2`,
`SERIAL2_BAUD=57`, and `BRD_SER2_RTSCTS=0`.

### New-laptop build prerequisites

Use Arduino IDE or Arduino CLI with:

* Board: **ESP32S3 Dev Module** (ESP32 Arduino core 2.0.17 was used here).
* Flash size: **8 MB** and partition scheme **Default 8 MB with SPIFFS**.
* ArduinoJson 6.x library.
* Official MAVLink C headers from `mavlink/c_library_v2`, installed as an
  Arduino library named `MAVLink`. Its `src` directory must contain `common/`;
  add a wrapper file `src/MAVLink.h` containing
  `#include <common/mavlink.h>`.

The bridge was built locally with these prerequisites. The first upload should
always be the receive-only probe, not the full cloud bridge.

## Validation already completed

* The GPIO18 receive-only probe compiles for `ESP32S3 Dev Module`.
* The full bridge compiles for `ESP32S3 Dev Module`.
* Cloud queue claim, completion, and telemetry tests pass locally.
* The project serial-baud test confirms the expected 57,600 bit/s setting.

## Not yet validated

* Neither sketch has been flashed during this handoff.
* A physical Pixhawk-to-ESP heartbeat has not yet been observed.
* No bidirectional command acknowledgement has been observed.
* No mission or flight test has been performed with this bridge.

Therefore the remaining unknown is now narrow: the physical UART wiring,
TELEM2 output configuration, board power/common ground, or the actual port
baud rate. It is no longer ambiguous which ESP GPIOs the firmware uses.

## Exact next steps

1. Connect only the three wires in the table above. Keep propellers removed.
2. Connect the ESP USB cable to the laptop and confirm that Windows exposes its
   CP210x COM port.
3. Flash the **receive-only probe** first.
4. Open its USB serial monitor at 115,200 baud. Expected output every few
   seconds is increasing RX bytes, valid MAVLink frames, and repeated
   `HEARTBEAT sys=...` lines.
5. If heartbeats appear, the Pixhawk-to-ESP direction and ground are proven.
6. Then flash the complete bridge. `STATUS` must report `Pixhawk link=fresh`
   before any cloud-command testing.
7. Only after a normal mission upload/ACK test should flight state-machine work
   be considered. Do not bypass Pixhawk pre-arm checks or fly this code merely
   because a mission upload succeeds.

## How to interpret the probe

| Probe result | Likely issue |
|---|---|
| `RX bytes=0` | TX-to-GPIO18 wire, shared GND, Pixhawk/TELEM2 power, or TELEM2 output disabled |
| RX bytes increase; valid MAVLink stays 0 | Wrong baud rate, corrupted signal, or wrong serial protocol |
| Heartbeats repeat | Physical receive path works; proceed to the full bridge |

See `docs/ESP_DRONE_CLOUD_BRIDGE.md` for cloud tokens and full bridge
provisioning. Never commit the Wi-Fi password or the private cloud tokens.

## Continuation brief for the next laptop / assistant

Copy the text below into the first message on the new laptop, then provide the
new assistant access to this repository checkout:

```text
Continue the VanniKawachh drone-mounted ESP32-S3 to Pixhawk TELEM2 bridge.
Read docs/DRONE_ESP_PIXHAWK_HANDOFF.md and docs/ESP_DRONE_CLOUD_BRIDGE.md
first. Do not assume hardware communication has been proven.

The sensing Raspberry Pi is separate. It sends server-verified distress events
to Render. The drone ESP is not a microphone node; it polls Render, receives
coordinates, and talks MAVLink to Pixhawk TELEM2.

Final UART wiring, with both boards powered off:
Pixhawk TELEM2 pin 2 TX -> ESP GPIO18
Pixhawk TELEM2 pin 3 RX -> ESP GPIO17
Pixhawk TELEM2 pin 6 GND -> ESP GND
No TELEM2 5 V, CTS, or RTS wire. Do not use ESP pins labelled TX/RX.

First flash firmware/drone_esp_uart_probe. It is receive-only and cannot arm
or command motors. Confirm repeated Pixhawk MAVLink HEARTBEAT lines at 57600
before using firmware/drone_esp. The full bridge uploads a mission only; it
does not arm or start AUTO flight.

Saved Pixhawk settings used by the bridge: SERIAL2_PROTOCOL=2,
SERIAL2_BAUD=57 (57600), BRD_SER2_RTSCTS=0. USB monitor is 115200.

New laptop build requirements: ESP32S3 Dev Module with 8 MB flash/default 8 MB
partition scheme, ArduinoJson 6.x, and the official MAVLink c_library_v2
headers installed as an Arduino library. See the handoff document for the
required MAVLink.h wrapper.

Do not overwrite unrelated dirty worktree changes. Do not request or put Wi-Fi
passwords / Render tokens into source code or Git. The next immediate task is
the passive heartbeat test after the ESP is connected through USB.
```

### Current repository scope

Files added for this bridge are:

* `firmware/drone_esp/` — full bridge firmware.
* `firmware/drone_esp_uart_probe/` — receive-only heartbeat test firmware.
* `docs/ESP_DRONE_CLOUD_BRIDGE.md` — cloud setup and bridge design.
* This handoff document.
* `tests/test_drone_esp_relay.py` — cloud-queue software checks.

There are unrelated modified and untracked project files in the worktree from
earlier work. Preserve them. The bridge commit is deliberately limited to the
files listed above plus the necessary `hub/edge_relay.py` and `hub/webapp.py`
cloud endpoints.
