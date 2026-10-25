# Drone ESP cloud to Pixhawk bridge

This is a separate ESP32-S3 mounted on the drone. It does not run a microphone
or the sensing-node model.

```
Sensing Raspberry Pi microphone -> Stage 1 candidate WAV
  -> Render /phone-alert runs its audio verification
  -> private, one-time drone command if distress is confirmed
  -> drone ESP polls /edge/drone/claim/next
  -> ESP uploads takeoff / target / RTL mission through Pixhawk TELEM2
  -> Pixhawk MISSION_ACK -> ESP reports result and telemetry to Render
```

The first bridge validates cloud delivery and bidirectional MAVLink mission
transfer. It does **not** arm Pixhawk or start AUTO flight. `MISSION_ACK=0`
means the plan was stored, not flown. The old Pi flight service is not used
by this path. The sensing Pi's USB microphone listener sends WAV audio to
`/phone-alert`; only a Render-confirmed incident sent with the private sensing
token enters the drone ESP queue. The existing public `/node-alert` route
remains a candidate/dashboard route and cannot queue this ESP.

## Wiring

The saved Pixhawk parameters show `SERIAL2_PROTOCOL=2` (MAVLink 2),
`SERIAL2_BAUD=57` (57,600 bit/s), and `BRD_SER2_RTSCTS=0`.

| Pixhawk TELEM2 pin | Drone ESP32-S3 header |
|---|---|
| 2, TX | GPIO18, ESP RX |
| 3, RX | GPIO17, ESP TX |
| 6, GND | GND |

Do not connect TELEM2 pin 1 (5 V) to an ESP GPIO. Leave pins 4 and 5
(CTS/RTS) open. Power Pixhawk and ESP normally, with only the signal ground
shared. Use the numbered GPIO17 and GPIO18 pins, not the pins printed `TX`
and `RX`: the printed pins are GPIO43/GPIO44 and share the onboard USB-to-UART
chip. With MAVLink on GPIO17/18, the ESP's USB-to-UART connector can again
be used for flashing and serial monitoring. The first hardware check should flash the passive
`firmware/drone_esp_uart_probe` sketch and confirm repeatable Pixhawk
heartbeats before flashing the full cloud bridge.

## Private configuration

Generate two independent random tokens, each at least 32 characters. Set
`VANNI_SENSING_TOKEN` and `VANNI_DRONE_ESP_TOKEN` as private Render environment
variables. Set the same `VANNI_SENSING_TOKEN` in the sensing Pi service
environment. Provision the drone ESP over its USB serial monitor at 115200:

```
WIFI <hotspot SSID>|<hotspot password>
TOKEN <VANNI_DRONE_ESP_TOKEN>
STATUS
```

The ESP saves Wi-Fi and token values in NVS. Do not put secrets in the sketch
or commit them to Git. It uses TLS with the Google Trust Services roots
bundled in `firmware/drone_esp/gts_roots.h` and waits for network time before
polling. The firmware requires the official MAVLink 2 C headers and
ArduinoJson 6. Both libraries were installed in this machine's Arduino
sketchbook. Build `firmware/drone_esp/drone_esp.ino` as an ESP32-S3 Dev Module.

## First hardware check

With propellers removed, ESP powered by USB, Pixhawk powered normally, and
TELEM2 5 V disconnected, upload `firmware/drone_esp_uart_probe` first. It is
receive-only: GPIO18 listens at 57,600 baud and GPIO17 is not driven. The
115,200-baud USB serial monitor should print repeated `HEARTBEAT` lines and
increasing valid-MAVLink counts. Zero bytes means wiring/port/power/baud is
still wrong; increasing bytes but zero valid messages suggests baud or signal
integrity. This is the physical link test that software simulation cannot do.

After that test succeeds, upload `firmware/drone_esp` and use `STATUS` in the
USB serial monitor. Firmware compilation and the cloud queue tests have passed
on the development laptop, but no ESP/Pixhawk heartbeat has yet been observed.

## What to observe

`STATUS` on the ESP serial monitor shows Wi-Fi, TLS time, Pixhawk heartbeat,
GPS fix, satellites, and whether a command is active. The public
`GET /edge/drone/status` returns a redacted copy of the last telemetry and
the latest command result. The ESP accepts only a fresh claimed command. It
uploads a mission only if Pixhawk is disarmed, has fresh MAVLink heartbeat and
position, has at least a 3D fix and six satellites, and the destination is
within 30 m of Pixhawk's reported location. The mission uses 3 m relative
takeoff height, a target waypoint with a two-second hold, and RTL. A command
expires if the link is not ready in 30 seconds. A rejected or timed-out
upload is reported to Render.

The ESP does not use a hard-coded home coordinate; it checks the current
Pixhawk GPS position. This path still needs a battery source, flight-mode
state machine, arm acknowledgement, mission-start acknowledgement, recovery
supervision, and field validation before an automatic physical launch is
appropriate. It also has no obstacle avoidance. A successful mission upload
is only the first communication milestone.

References: [ArduPilot telemetry port setup](https://ardupilot.org/copter/docs/common-telemetry-port-setup.html),
[Pixhawk port pinout](https://ardupilot.org/copter/docs/common-pixhawk-overview.html),
[MAVLink mission protocol](https://mavlink.io/en/services/mission.html),
[ArduCopter AUTO mode](https://ardupilot.org/copter/docs/auto-mode.html).
