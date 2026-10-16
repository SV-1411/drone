# ESP32-S3 flight relay

This firmware replaces the Pi's cloud-command consumer. Render still verifies
voice reports and the dashboard operator still approves a mission. Raw sound,
button-test and unapproved reports cannot start the flight controller.

## Wiring

Connect everything unpowered, with propellers removed.

| Pixhawk 2.4.8 TELEM2 | ESP32-S3 labelled pin |
|---|---|
| Pin 2 TX | RX / GPIO44 |
| Pin 3 RX | TX / GPIO43 |
| Pin 6 GND | GND |
| Pin 1 +5V, Pin 4 CTS, Pin 5 RTS | Unconnected during USB-powered bench verification |

Use the S3's native USB connector for provisioning. The other USB-to-UART
connector, if present, may share GPIO43/44 and must not drive the Pixhawk UART.
UART data is 3.3V. Never connect 5V to a 3V3/GPIO pin. Independent power for
flight must be validated for the board; USB bench power proves no redundancy.

## Build

Pinned PlatformIO environment: ESP32-S3, 8 MB flash, OPI PSRAM, USB CDC on boot.

```powershell
.\.cache\esp32-tools\Scripts\python.exe -m platformio run -d firmware\flight_relay
```

Tool dependencies: PlatformIO 6.1.18, esptool 4.10.0, pyserial. Host policy tests
are compiled with Zig 0.14.1 (`python -m ziglang c++ -std=c++17 -I
firmware/flight_relay/include firmware/flight_relay/test/test_policy.cpp -o
.cache/test_esp32_policy.exe`). The generated executable must pass before flash.

## Private provisioning

For the simplest private key entry, start
`python scripts/esp32_setup_server.py` with the tool interpreter below, then
open `http://127.0.0.1:8767/`. It accepts the existing dashboard operator key,
saves it over COM12, and stops after successful provisioning. It retains Wi-Fi
settings and does not commission flight.

Do not put credentials into source or chat. With the drone disarmed and props
removed, use the isolated tool interpreter:

```powershell
.\.cache\esp32-tools\Scripts\python.exe scripts\provision_esp32_relay.py --current-wifi
.\.cache\esp32-tools\Scripts\python.exe scripts\provision_esp32_relay.py --status
.\.cache\esp32-tools\Scripts\python.exe scripts\provision_esp32_relay.py --authcheck
```

The current Wi-Fi profile is exported into a temporary directory internally,
read without displaying its password, then removed. ESP32-S3 requires 2.4 GHz.
The prompt uses the same operator key already entered on the dashboard. There
is no separate Pi or device token to obtain. Use `--wifi-only` to provision Wi-Fi
before entering that key. Add `--cells 3` only after confirming a 3S pack.
Credentials are stored in the separate `vanni-flight` NVS namespace.

An operator-approved phone command uses `POST /edge/real-test/claim/next` and
must contain `created`/`expires_at` from the accompanying relay update. Commands
from an older cloud deployment are rejected. `authcheck` uses a read-only GET,
does not claim commands, and reports only HTTP status. TLS validation requires
the bundled GTS roots and a synchronized clock; certificate errors fail closed.

## Limits and local flight lock

Bench firmware starts flight-locked. After validated commissioning, real mode
can persist across ordinary restarts and execute each newly approved incident
without a USB authorization per mission. An interrupted flight always requires
local recovery. Initial targets are at most
20 m away and total mission time is 120 seconds. Normal flight requests 1 m
relative to launch home and 0.5 m/s horizontal speed, then a same-altitude return
waypoint and LAND. No automatic payload release or observation hover.
Actual altitude/speed can deviate, terrain is not measured, and onboard failsafes
retain authority. No obstacle avoidance is provided.

The existing Pixhawk log showed a battery failsafe that disarmed after throttle
increased. Correct the battery/measurement issue and verify manual flight and RC
takeover before flight authorization. This firmware does not relax pre-arm or
battery checks. Its conservative preflight requires known battery cells,
at least 3.7V/cell, known battery percentage >=30, 3D GPS with 8 satellites,
fresh grounded home, healthy RC/EKF and Pixhawk pre-arm status.

ArduCopter 4.7 parameters observed on this aircraft use SI units:

| Parameter | Required for this profile |
|---|---|
| `SERIAL2_PROTOCOL` | 2 (MAVLink2) |
| `SERIAL2_BAUD` | 57 (57600 baud) |
| `BRD_SER2_RTSCTS` | 0 (no hardware flow control) |
| `WP_SPD` | 0.5 m/s |
| `WP_SPD_UP` | <=0.5 m/s, positive |
| `WP_SPD_DN` | <=0.5 m/s, positive |
| `LAND_SPD_MS` | <=0.5 m/s, positive |
| `MAV_GCS_SYSID` | 246 (ESP heartbeat source) |
| `FS_GCS_ENABLE` | 5 (LAND), independently tested before commissioning |

Firmware reads these values; it does not write them. Older firmware names and
units differ. Read current parameters instead of copying values blindly.
Onboard return/failsafe altitude must be evaluated separately: normal RTL can
climb above 1 m. The firmware cannot guarantee a 1 m physical ceiling.

After all actual readiness work is complete, a locally attached USB console can
send a single JSON line with `op=authorize`, `pilot_ready=true`,
`manual_flight_validated=true`, and `link_failsafe_tested=true`. This grants
one approved mission within 120 seconds if current preflight passes. This
command is never sent by the provisioning helper or automated bench tests.
For ongoing operation, the local `commission` operation requires the same
readiness confirmations plus `battery_calibrated=true` and passing live
preflight. It saves real mode and continues listening for dashboard-approved
incidents across reboots. This commissioning operation is not executed during
bench setup. Reprovisioning settings or `lock` clears saved real mode.
`{"op":"lock"}` removes authorization and requests LAND if ESP owns an active
flight. Do not open/reset USB serial while flying; it may reset the ESP.

## Failure behavior

MAVLink supervision runs independently of HTTPS. It requires command ACKs and
observed modes/arming. Low battery, GPS/EKF/RC loss or timeout requests LAND;
there is no in-air disarm command. An unexpected Pixhawk mode means pilot or
onboard failsafe takeover: the ESP stops navigation commands and stays busy
until grounded/disarmed telemetry confirms the end. Wi-Fi loss does not block
local navigation, return or landing. Lost UART falls back to independently
configured Pixhawk link-loss behavior.

Accepted command IDs are persisted before any flight command. A reset with an
unfinished command requires local `{"op":"recover"}` with fresh grounded,
disarmed telemetry; reboot never resumes an interrupted flight. A queued cloud
result is retried before claiming new commands. The existing relay is still
ephemeral SQLite and cannot provide durable emergency dispatch guarantees.

Full original 8MB firmware/NVS backup is retained in ignored `.cache/` and may
contain credentials. Keep it private. Restoring the firmware does not establish
aircraft readiness.
