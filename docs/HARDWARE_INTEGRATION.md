# Hardware Integration Guide

How to move this system off the SITL simulator and onto a real autonomous drone.
The codebase is deliberately structured so that swapping the simulator for hardware
is a configuration change, not a code change — but the *aircraft* itself needs
careful setup so it can fly safely without a human in the loop.

> **Safety statement.** Autonomous flight is regulated almost everywhere. Before
> any field test, confirm you have the appropriate authorization (CAA / FAA /
> DGCA / EASA — whichever applies to your jurisdiction), insurance, an
> over-the-air kill switch, and a visual observer. This guide assumes you have
> those covered.

---

## 1. Bill of materials

A minimum viable autonomous platform that this software can drive:

| Subsystem | Recommended part | Why it matters |
|---|---|---|
| **Airframe** | 450-mm class quadcopter (e.g. F450, S500) | Big enough for a GPS mast clear of motor interference, small enough to be safe |
| **Flight controller** | Pixhawk 4, Pixhawk 6C, Cube Orange+, or Holybro Durandal | Must run ArduPilot (Copter ≥ 4.3). PX4 also works with minor tweaks to the mode names. |
| **GPS / compass** | Here3+, M9N, or Holybro M10 | RTK optional but recommended if you need < 1 m accuracy at the target |
| **Companion computer** | Raspberry Pi 4 (4 GB+), Pi 5, NVIDIA Jetson Nano, or Orange Pi 5 | Runs `flight_core` + `trigger_api` and talks MAVLink to the FC. RPi 4 is the cheapest option that comfortably handles the dashboard webserver too. |
| **Telemetry radio (optional)** | RFD900x / SiK 915 MHz pair, *or* 4G modem on the companion computer | Lets the ground crew see the dashboard and trigger missions from far away. |
| **Battery** | 4S 5200 mAh LiPo + power module that feeds voltage/current back to the FC | Real `LOW_BATTERY_PCT` failsafes need a calibrated power module — without it the % is a guess. |
| **RC receiver + transmitter** | FrSky / RadioMaster + ELRS or any S.BUS receiver | *Even though the mission is autonomous*, you MUST have a transmitter with a mode switch and an arm/disarm switch as the kill path. See §6. |
| **ESCs + motors** | Sized for the airframe; any BLHeli32 ESC + 920–1000 kV motors are fine | — |

Total hardware cost as of 2026: roughly $450–$900 depending on FC and GPS choices.

---

## 2. Physical wiring

```
                ┌─────────────────────────┐
                │   GPS + compass (UART)  │
                └──────────┬──────────────┘
                           │ Serial
   ┌─────────────────┐     │
   │ RC Receiver SBUS├─────┤
   └─────────────────┘     │             ┌──────────────────────┐
                           │             │ Companion computer   │
                ┌──────────┴──────┐  ←── │ (RPi / Jetson)       │
                │  Flight         │ MAVLink (TELEM2 / USB)      │
                │  Controller     │  ──→ │  Runs flight_core +  │
                │  (Pixhawk)      │      │  trigger_api +       │
                └──────────┬──────┘      │  dashboard           │
                           │             └──────────┬───────────┘
                ┌──────────┴──────┐                 │ Wi-Fi / 4G
                │ Power module    │                 ▼
                │ + 4S battery    │            Ground crew
                └─────────────────┘            (viewer dashboard,
                                                /trigger API)
```

Key cable runs:

- **Flight controller ↔ companion computer**: TELEM2 UART (3.3 V logic) on the FC
  to the UART pins on the companion computer (RPi GPIO 14/15, ttyAMA0). Use 921600 baud.
  USB also works and is simpler for benchtop dev — `/dev/ttyACM0` on Linux.
- **GPS ↔ flight controller**: dedicated GPS port. Mount the GPS antenna on a mast
  ≥ 10 cm above the power wires so the compass isn't drowned by motor current.
- **Receiver ↔ flight controller**: S.BUS to the RC IN port. The transmitter
  provides the manual override / kill path described in §6.
- **Power module ↔ flight controller**: PM02 / PM07 between the battery and the
  ESCs, with the sense lead going to the FC POWER port. This is what makes
  `vehicle.battery.level` meaningful.

---

## 3. Companion-computer software setup

On a fresh Raspberry Pi OS Lite (64-bit) or Ubuntu 22.04 image:

```bash
sudo apt update && sudo apt install -y python3.11-venv git build-essential libxml2-dev libxslt1-dev
git clone <your-repo> drone-safety-system && cd drone-safety-system
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Enable serial on the Pi (so the UART is accessible):

```bash
sudo raspi-config nonint do_serial 2     # disable console, keep hardware UART
sudo systemctl disable hciuart           # free up the primary UART
sudo reboot
```

Verify MAVLink data is flowing in:

```bash
python -m pymavlink.tools.mavproxy --master=/dev/serial0 --baudrate=921600
# you should see: "online system 1" within a few seconds
```

---

## 4. Pointing this codebase at the real flight controller

Only one thing changes: the `MAVLINK_CONNECTION` env var.

| Scenario | `MAVLINK_CONNECTION` |
|---|---|
| SITL (today) | `tcp:127.0.0.1:5760` |
| FC over USB on RPi | `/dev/ttyACM0,921600` |
| FC over TELEM2 UART on RPi | `/dev/serial0,921600` |
| FC over telemetry radio on RPi | `/dev/ttyUSB0,57600` |
| Companion → ground over UDP | `udp:0.0.0.0:14550` (on ground); rebroadcast from companion with mavproxy |

`flight_core/config.py` already reads this from the environment, so all that's
needed on the companion computer is:

```bash
export MAVLINK_CONNECTION=/dev/serial0,921600
export HOME_LAT=<your home pad latitude>
export HOME_LON=<your home pad longitude>
export CRUISE_ALT=25                # higher than 15 m for real obstacles
export GEOFENCE_RADIUS=300          # tighten to your authorized area
export LOW_BATTERY_PCT=30
export CRIT_BATTERY_PCT=20
python -m uvicorn trigger_api.main:app --host 0.0.0.0 --port 8000
```

Put those env vars in a systemd unit so the service comes up on boot — see
`docs/systemd-trigger-api.service.example` in §10.

---

## 5. ArduPilot parameters — **REMOVE the SITL relaxations**

`flight_core/mission_executor.py` contains a helper called
`_relax_sitl_arming_checks()` that sets:

```
ARMING_CHECK   = 0      # disables ALL pre-arm safety checks
FS_THR_ENABLE  = 0      # disables RC throttle failsafe
GPS_HDOP_GOOD  = 100.0  # accepts terrible GPS
```

**Those values are catastrophic on a real airframe.** Real-aircraft values to
set via Mission Planner / QGroundControl or `vehicle.parameters` before first
flight:

| Parameter | Real-flight value | Why |
|---|---|---|
| `ARMING_CHECK` | `1` (all checks on) | Pre-arm protects you from arming with bad GPS, low battery, miscalibrated sensors |
| `FS_THR_ENABLE` | `1` (enabled, return) | If RC link is lost, return home |
| `FS_THR_VALUE` | `975` | The PWM value below which throttle failsafe trips |
| `FS_GCS_ENABLE` | `2` (continue mission in AUTO, RTL otherwise) | If GCS heartbeat is lost > 5 s, fall back to safe behavior |
| `FS_EKF_THRESH` | `0.8` | If EKF variance spikes, trigger failsafe |
| `BATT_FS_LOW_ACT` | `2` (RTL) | Low-battery failsafe action |
| `BATT_FS_CRT_ACT` | `1` (LAND) | Critical-battery failsafe action |
| `BATT_LOW_VOLT` | calibrated to your pack | e.g. 14.0 V for a 4S pack |
| `BATT_CRT_VOLT` | calibrated to your pack | e.g. 13.2 V for a 4S pack |
| `RTL_ALT` | `1500` (15 m, cm units) | Climb to this altitude before returning, to clear obstacles |
| `RTL_ALT_FINAL` | `0` (land) | Land at home, don't hover |
| `WPNAV_SPEED` | `500` (5 m/s) for first flights | Slower = safer while you debug |
| `WPNAV_RADIUS` | `200` (2 m) | "Reached waypoint" tolerance the FC uses internally — keep tighter than `WAYPOINT_TOLERANCE` in our config |
| `GPS_HDOP_GOOD` | `1.4` (default) or tighter | Reject takeoff if GPS quality is poor |
| `FENCE_ENABLE` | `1` | Hardware geofence as a second layer over our software one |
| `FENCE_TYPE` | `7` (alt + circle + polygon) | All three fence types |
| `FENCE_RADIUS` | match `GEOFENCE_RADIUS` env var | Belt-and-braces |
| `FENCE_ACTION` | `1` (RTL) | What to do on breach |

Critically, edit `mission_executor.py` so the SITL relaxer is a no-op in production. The cleanest way:

```python
# In flight_core/mission_executor.py
import os
SITL_MODE = os.environ.get("SITL_MODE", "0") == "1"

def _relax_sitl_arming_checks(self) -> None:
    if not SITL_MODE:
        return
    # …existing body…
```

Then set `SITL_MODE=1` only when launching against `dronekit-sitl`, and leave it
unset on the real airframe. The flight will then go through full pre-arm gating
just like a piloted ArduPilot mission.

---

## 6. The mandatory manual kill path (yes, even for an autonomous mission)

"No human in the loop for normal flight" does **not** mean "no human is able to
abort." Standard practice — and in most jurisdictions, the law — is that a
qualified pilot in command must be able to override the autonomous controller
at any moment.

Wire your RC transmitter so that:

1. **Mode switch** — a 3-position switch on the transmitter is mapped to
   `STABILIZE` / `GUIDED` / `RTL`. Default position is `GUIDED` so our
   `trigger_api` can drive the drone. Flipping to `STABILIZE` returns control
   to the pilot's sticks; `RTL` aborts the mission and returns home.
2. **Arm/disarm switch** — a momentary switch wired to `RCx_OPTION = 41`
   (Arm/Disarm). A hold-down disarms instantly. This is your kill switch.
3. **Throttle failsafe** — `FS_THR_ENABLE=1` causes RTL when the transmitter
   goes out of range, so an obstacle blocking your link doesn't strand the
   drone.

The autonomous mission described by the README still works exactly as it does
in SITL — the moment the pilot flips the mode switch, ArduPilot ignores any
`GUIDED` commands from our code and the human is in command.

---

## 7. Pre-flight calibration checklist

These must be done once per airframe build, and re-verified before every flight
day:

- [ ] Accelerometer calibration (`Initial Setup → Calibrate Accel` in Mission Planner)
- [ ] Compass calibration, *with motors running mid-throttle* (compass-motor calibration) — this is what stops yaw drift in autonomous flight
- [ ] Radio calibration (full stick travel)
- [ ] ESC calibration (so all motors arm with identical PWM curves)
- [ ] Level horizon
- [ ] Voltage / current sensor calibration against a known reference
- [ ] GPS HDOP check on the ground — should be < 1.5 with > 9 satellites before takeoff
- [ ] EKF status green (Mission Planner → Status tab)
- [ ] Mission Planner pre-arm message is clean

Save the parameter file *after* calibration so you can reflash if the FC dies.

---

## 8. First autonomous flight — recommended progression

Don't go from "SITL passes" to "fly 1 km autonomous" in one step. Suggested
progression:

1. **Bench test (props removed).** Run `tests/test_full_mission.py` pointed at
   the real FC over USB with props off. Verify the motors spin in response to
   arming + simulated takeoff. Confirm modes change, log lines look right.
2. **Tethered hover.** Props on, drone tied to a sandbag with 2 m of line.
   Trigger a 2-m altitude, 0-m lateral mission. Confirm hover stability and
   that RTL works.
3. **Open-field GUIDED hover.** Take off in `STABILIZE` manually, switch to
   `GUIDED`, send a `simple_goto` to a target 10 m away. Switch back to
   `STABILIZE` and land manually.
4. **Full autonomous mission, short range.** Trigger via our API with a target
   30 m from home, alt 10 m, hover 10 s, then RTL. Pilot stands by with the
   kill switch.
5. **Production range.** Only after several clean short-range runs do you push
   to the distances in `GEOFENCE_RADIUS`.

---

## 9. Failsafes you should add for real-aircraft use

The current `failsafe_handler.py` already covers:

- low battery (% based, RTL) and critical battery (LAND, never downgraded —
  escalates even mid-RTL)
- GPS loss (debounced over `GPS_BAD_SAMPLES` consecutive seconds → LAND)
- geofence breach (RTL; targets outside the fence are also rejected at the
  API edge before flight)
- mission timeout (RTL) and per-leg stall detection
- **MAVLink link loss** — `vehicle.last_heartbeat` older than
  `LINK_LOSS_TIMEOUT` (default 10 s) aborts the mission, since every other
  reading the monitor makes would be frozen data
- absent battery telemetry is detected and logged loudly ("battery failsafes
  INACTIVE") — on real hardware, treat that warning as a no-go for dispatch

For real flight, extend it (or set the equivalent ArduPilot parameters from
§5) to also handle:

- **EKF failsafe** — `vehicle.ekf_ok` should be polled; on `False`, immediate
  LAND. Real airframes can lose EKF in flight if compass interference spikes.
- **GCS heartbeat failsafe** — if the companion computer crashes, ArduPilot's
  `FS_GCS_ENABLE` makes the FC RTL on its own after 5 s of silence.
- **Wind / vibration sanity** — `vehicle.vibration` should be sampled before
  every mission. A reading above ~30 m/s² on any axis means a damaged motor
  mount; refuse to dispatch.
- **Maximum tilt angle** — `ANGLE_MAX = 3500` (35°) is plenty for autonomous
  cruise. Higher than that and you risk falling out of the sky in wind.

A clean way to wire these into the existing handler:

```python
# in flight_core/failsafe_handler.py
def _check_ekf(self) -> None:
    if not self.vehicle.ekf_ok:
        self._emit(FailsafeEvent("ekf_lost", "EKF reported unhealthy", action="LAND"))

def _check_vibe(self) -> None:
    v = self.vehicle.vibration
    if v is None: return
    if max(v.x, v.y, v.z) > 30.0:
        self._emit(FailsafeEvent("high_vibration", f"vibe={v}", action="LAND"))
```

---

## 10. Production deployment on the companion computer

`/etc/systemd/system/drone-trigger-api.service`:

```ini
[Unit]
Description=Autonomous drone trigger API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/drone-safety-system
EnvironmentFile=/etc/drone-safety.env
ExecStart=/home/pi/drone-safety-system/.venv/bin/python -m uvicorn trigger_api.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`/etc/drone-safety.env`:

```bash
MAVLINK_CONNECTION=/dev/serial0,921600
HOME_LAT=<pad latitude>
HOME_LON=<pad longitude>
HOME_ALT=<elevation in metres>
CRUISE_ALT=25
HOVER_DURATION=30
WAYPOINT_TOLERANCE=3
LOW_BATTERY_PCT=30
CRIT_BATTERY_PCT=20
GEOFENCE_RADIUS=300
MAX_MISSION_DURATION=600
TELEMETRY_INTERVAL_MS=500
# SITL_MODE intentionally unset — production goes through full pre-arm
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now drone-trigger-api
sudo journalctl -u drone-trigger-api -f
```

---

## 11. From dashboard to remote operations

The dashboard talks to the API over HTTP + WebSocket. For a production setup:

- Put the dashboard behind nginx with TLS on the companion computer.
- Restrict the `POST /trigger` endpoint with an API key header (add a simple
  dependency in `trigger_api/main.py` that reads `X-API-Key` and compares it
  with an env var).
- Configure your 4G modem to publish a static IP or use a Tailscale/WireGuard
  tunnel so the ground crew dashboard can reach the drone over the public
  internet without exposing port 8000 to the world.

---

## 12. Quick switchover summary

| Step | Action |
|---|---|
| 1 | Flash ArduCopter ≥ 4.3 on the flight controller |
| 2 | Apply the parameter file from §5 |
| 3 | Calibrate accel / compass / radio / ESC (§7) |
| 4 | Wire companion computer to TELEM2 |
| 5 | `git clone` this repo on the companion computer |
| 6 | `pip install -r requirements.txt` |
| 7 | Set `MAVLINK_CONNECTION` and other env vars in `/etc/drone-safety.env` |
| 8 | Make the SITL relaxer no-op in production (§5) |
| 9 | Enable the systemd unit (§10) |
| 10 | Bench → tethered → short autonomous → full autonomous (§8) |

Once that's done the trigger interface, the WebSocket telemetry, the dashboard,
the queue, and the failsafe monitor all behave exactly as they do in SITL —
because none of them know they're talking to a real aircraft.
