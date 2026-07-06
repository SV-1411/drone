# VanniKawachh Build & Operations Guide — From Empty Bench to Autonomous Response

This guide takes you from **nothing** to a flying, autonomously-dispatched
quadcopter running this codebase — and, new in v2, to the VanniKawachh
sensing layer that dispatches it: the hub in simulation and on a Raspberry
Pi 5, the ESP32 firmware, and the full-chain Phase-0 demo (§10), plus the
Phase 1–4 hardware bring-up order (§11). It covers what to buy (with a
minimum budget), what to download, how to assemble the airframe, how to
connect the software to the aircraft, how to run the system, and how
missions are commanded and recalled.

It complements two other documents:

- [`HARDWARE_INTEGRATION.md`](HARDWARE_INTEGRATION.md) — deep detail on
  wiring pinouts, ArduPilot parameters, calibration, and the SITL→real
  switchover. Referenced throughout.
- [`SYSTEM_DOCUMENTATION.md`](SYSTEM_DOCUMENTATION.md) — the software
  reference (API, configuration, failsafes).

> **Safety and legality first.** In India, civil drone operation is governed
> by the Drone Rules, 2021 (as amended): most builds in this class fall in
> the *Small* category (2–25 kg) or *Micro* (250 g–2 kg), require
> registration on the DigitalSky platform (UIN), and may only fly in
> permitted zones — check the airspace map before every flight. Equivalent
> rules exist elsewhere (FAA Part 107 in the US, EASA in the EU). Autonomous
> does **not** mean unsupervised: keep a trained pilot with an RC
> transmitter and a kill switch within visual line of sight for every
> flight described here.

---

## 1. What to buy — bill of materials with budget

Three tiers. The **Minimum** tier is the cheapest configuration that can
safely run this stack; prices are indicative Indian retail (mid-2026,
robu.in / robokits / Amazon.in class sellers) and will drift — treat them
as ±20%.

### 1.1 Minimum-budget build (~₹36,000 / ~US$430)

| # | Item | Spec / example | Qty | Est. price (₹) |
|---|---|---|---|---|
| 1 | Frame | F450-class glass-fibre quad frame with integrated PDB | 1 | 1,200 |
| 2 | Flight controller | Pixhawk 2.4.8 (open-hardware FMUv2/v3 derivative) with buzzer + safety switch | 1 | 10,500 |
| 3 | GPS + compass | u-blox NEO-M8N module with stand | 1 | 2,500 |
| 4 | Motors | 2212 920 kV brushless | 4 | 2,400 |
| 5 | ESCs | 30 A (SimonK/BLHeli), 3S-capable | 4 | 2,200 |
| 6 | Propellers | 10×4.5 (1045) self-locking, + spares | 2 sets | 700 |
| 7 | Battery | 3S 5200 mAh 35C LiPo, XT60 | 1 | 3,800 |
| 8 | Power module | APM/Pixhawk power module (voltage+current sense, XT60) | 1 | 800 |
| 9 | RC transmitter + receiver | FlySky FS-i6 + FS-iA6B (6 ch, iBUS/PPM) | 1 | 4,800 |
| 10 | Companion computer | Raspberry Pi Zero 2 W + 32 GB card + UART cable | 1 | 3,200 |
| 11 | LiPo charger | IMAX B6-class balance charger + supply | 1 | 2,600 |
| 12 | Consumables | XT60 pairs, 14 AWG silicone wire, heat-shrink, zip ties, foam tape, velcro strap, thread-lock | — | 900 |
| | **Total** | | | **≈ ₹35,600** |

Notes on the minimum tier:

- The Pixhawk 2.4.8 is the budget workhorse: it runs current ArduPilot
  Copter 4.x, exposes TELEM2 for the companion computer, and has the same
  parameter surface as the expensive boards. Its IMUs are older — fine for
  this mission profile.
- A Pi Zero 2 W is enough to run `flight_core` + `trigger_api` (the stack
  is a few threads and an HTTP server). If you want the dashboard *served
  from the aircraft* too, step up to a Pi 4 (2 GB) for ~₹800 more.
- One battery means ~10–12 min of flight per charging cycle. A second
  battery (+₹3,800) doubles your testing throughput and is the single best
  upgrade.

### 1.2 Recommended build (~₹58,000)

Everything above, with these substitutions/additions:

| Change | Why | Δ price (₹) |
|---|---|---|
| Pixhawk 6C / Cube Orange Lite instead of 2.4.8 | Current-gen IMUs, better EKF behaviour, vibration isolation | +9,000 |
| M9N/M10 GPS instead of M8N | Faster fix, better multipath rejection | +1,500 |
| Raspberry Pi 4 (4 GB) instead of Zero 2 W | Headroom for camera streaming + onboard dashboard | +3,500 |
| Second 5200 mAh battery | Continuous test cycles | +3,800 |
| 433 MHz / 915 MHz telemetry radio pair (SiK) | Live telemetry + parameter access from the bench without USB | +3,500 |
| Spare props ×4 sets, spare motor ×1 | You will break props learning | +1,200 |

### 1.3 What you intentionally do NOT need

- **No gimbal** — the Pi Camera Module 3 *is* part of the v2 build (Phase 4
  hover evidence recording, `SYSTEM_DOCUMENTATION.md` §17), but it mounts
  fixed; a stabilised gimbal is unnecessary for this mission profile.
- **No lidar/optical flow** — GPS-denied flight is out of scope (see
  thesis §Future Work).
- **No 4G/LTE link for the first build** — operate on local Wi-Fi from the
  Pi; add a 4G HAT (~₹4,500) when you need beyond-Wi-Fi range and have the
  regulatory approvals for it.

---

## 2. What to download

| Software | Where | Used for |
|---|---|---|
| **ArduPilot Copter 4.x firmware** | firmware.ardupilot.org (via Mission Planner / QGC installer) | The autopilot itself |
| **Mission Planner** (Windows) or **QGroundControl** (any OS) | ardupilot.org / qgroundcontrol.com | Firmware flash, calibration, parameter editing. Used for SETUP ONLY — this project's runtime never needs it |
| **Raspberry Pi OS Lite (64-bit)** | raspberrypi.com | Companion computer OS |
| **This repository** | `git clone https://github.com/SV-1411/drone.git` | The dispatch stack |
| **Python 3.10+** | python.org / `apt install python3` | Runtime for flight_core + trigger_api |
| **Node.js 18+** | nodejs.org (only where the dashboard is built) | Dashboard build |
| **Docker Desktop** *(optional)* | docker.com | Containerised SITL/API/dashboard for development machines |

Nothing else. The runtime deliberately has no cloud dependency: the
aircraft + a laptop on the same network is a complete system.

---

## 3. Building the airframe

Total bench time for a first build: ~6–8 hours. Work in this order so each
stage is testable before the next hides it.

### 3.1 Frame and propulsion

1. **Assemble the frame** per its manual: arms to bottom plate (the plate
   is usually the power-distribution board — orient solder pads outward),
   then standoffs. Use thread-lock on every metal-into-metal screw; motor
   vibration will undo dry screws in one flight.
2. **Mount motors** to the arms (M3 screws, thread-locked). Do not fit
   propellers yet — props stay OFF until §6 arming tests are done.
3. **Solder ESCs** to the PDB pads (red→+, black→−), and the **power
   module's** XT60 pigtail to the PDB input. Tug-test every joint.
4. **Motor-to-ESC**: connect the three bullet leads in any order for now —
   §6 fixes rotation direction by swapping any two.

### 3.2 Flight controller and sensors

5. **Mount the Pixhawk** at the frame's centre of gravity on the supplied
   vibration foam, arrow facing forward.
6. **GPS mast**: mount the M8N on its stand at the rear, arrow also facing
   forward (the module contains the compass — misalignment = toilet-bowling).
7. Connect per the wiring table in
   [`HARDWARE_INTEGRATION.md` §2](HARDWARE_INTEGRATION.md): ESC signal
   leads → MAIN OUT 1–4 (Copter "Quad X" order: front-right, back-left,
   front-left, back-right), power module → POWER port, GPS → GPS +
   I²C/CAN port, buzzer + safety switch to their ports, receiver → RCIN
   (PPM/iBUS).

### 3.3 Companion computer

8. **Mount the Pi** with foam tape away from the power wiring (EMI), and
   wire `Pi UART TX→TELEM2 RX, RX→TELEM2 TX, GND→GND`. Power the Pi from
   a 5 V BEC (most PDBs have one) — **not** from the Pixhawk's rail.
9. Flash Raspberry Pi OS Lite, enable SSH + UART
   (`/boot/config.txt: enable_uart=1`, disable the serial console), then
   follow [`HARDWARE_INTEGRATION.md` §3](HARDWARE_INTEGRATION.md) to
   install this repo on the Pi.

### 3.4 Bench bring-up (no props!)

10. Flash **ArduCopter 4.x stable** via Mission Planner/QGC over USB.
11. Run the **mandatory calibrations** (accelerometer, compass, radio,
    ESC, battery monitor) — full checklist in
    [`HARDWARE_INTEGRATION.md` §7](HARDWARE_INTEGRATION.md).
12. Set the **real-hardware parameter set** from
    [`HARDWARE_INTEGRATION.md` §5](HARDWARE_INTEGRATION.md) — failsafes ON,
    geofence ON, RTL altitude, and **never** set `ARMING_CHECK=0` on a
    real aircraft. Leave `SITL_MODE` unset on the Pi so this codebase keeps
    ArduPilot's pre-arm gating in force.

---

## 4. Connecting this software to the drone

On the Pi (one-time):

```bash
git clone https://github.com/SV-1411/drone.git ~/drone-safety-system
cd ~/drone-safety-system
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Point the stack at the flight controller instead of SITL — that is the
**only** required change:

```bash
export MAVLINK_CONNECTION=/dev/serial0,921600   # TELEM2 UART
export HOME_LAT=<your pad latitude>
export HOME_LON=<your pad longitude>
export API_TOKEN=<a long random string>          # auth ON for real aircraft
# SITL_MODE deliberately NOT set
python -m uvicorn trigger_api.main:app --host 0.0.0.0 --port 8000
```

Connection-string cheatsheet:

| Link | `MAVLINK_CONNECTION` |
|---|---|
| Pi UART → TELEM2 (production) | `/dev/serial0,921600` |
| USB cable to Pixhawk (bench) | `/dev/ttyACM0,115200` |
| SiK telemetry radio | `/dev/ttyUSB0,57600` |
| SITL (development) | `tcp:127.0.0.1:5760` |

Verify with `curl http://<pi-ip>:8000/health` → `"vehicle_connected": true`.
For boot-on-power-up deployment (systemd unit), see
[`HARDWARE_INTEGRATION.md` §10](HARDWARE_INTEGRATION.md).

---

## 5. Running the system

| Scenario | Command |
|---|---|
| Pure simulation on a PC | `.\run_all.ps1` (Windows) or `docker compose up --build` |
| Hub in simulation (no hardware — synthetic node alerts) | `python -m hub.main --sim` — see §10.1 |
| **Full-chain Phase-0 demo** (sensing sim → hub → SITL flight) | `python scripts/demo_phase0.py` — see §10.2 |
| Automated acceptance test | `python tests/test_full_mission.py` |
| Unit tests (no SITL; includes hub tests) | `python -m pytest` |
| Real aircraft | API on the Pi (above) + dashboard on any laptop: `cd dashboard && npm install && npm run dev` with the Vite proxy pointed at the Pi (`API_UPSTREAM=http://<pi-ip>:8000 npm run dev`) |

Dashboard at `http://<laptop>:5173`; Swagger at `http://<pi-ip>:8000/docs`.

---

## 6. First flights — the non-negotiable progression

Detailed in [`HARDWARE_INTEGRATION.md` §8](HARDWARE_INTEGRATION.md); the
short form:

1. **Props-off arming test** — arm via RC in Stabilize on the bench;
   verify motor order and direction (swap two ESC leads to reverse).
2. **Manual hover** (props on, open field, pilot on RC) — verify stability
   and vibration levels before any autonomy.
3. **RC-commanded GUIDED test** — pilot holds the kill switch; a single
   `POST /trigger` with a target 30 m away at 10 m altitude.
4. **Tethered/short autonomous mission** — full trigger → hover → RTL
   cycle within 100 m.
5. **Operational missions** — expand range progressively; never beyond
   visual line of sight without the required authorisation.

## 7. "Maneuvering" — how this system is commanded

There is deliberately **no manual piloting** through this software. The
operator surface is exactly three verbs:

| Action | How | What the drone does |
|---|---|---|
| **Dispatch** | Dashboard form or `POST /trigger {lat, lon, priority, ...}` | Auto-arms, climbs to cruise altitude, flies to target, hovers, returns, lands |
| **Divert** | `POST /mission/{id}/waypoint {lat, lon}` | Inserts a detour into the running mission, then resumes the remaining hover |
| **Recall** | Dashboard *Cancel mission* button or `POST /mission/{id}/cancel` | Immediately abandons the mission and returns home; the queue stays blocked until it has landed and disarmed |

Everything else is automatic, including the failsafe ladder (battery → RTL
/ LAND, GPS loss → LAND after debounce, geofence → RTL, stall → RTL,
timeout → RTL). The *pilot's* override is the RC transmitter: flipping the
mode switch out of GUIDED/RTL takes authority away from this software
instantly, and the kill switch cuts motors — that path is hardware-level
and cannot be blocked by anything in this stack.

## 8. Operating costs and maintenance

- **Per-flight cost** is essentially battery wear: a 5200 mAh 3S LiPo is
  good for ~200–300 cycles; ~₹15–20 per flight amortised.
- **Props** are consumables — inspect for chips before every flight.
- **Battery discipline**: never below 3.5 V/cell in flight (the 20%
  failsafe enforces this), store at 3.8 V/cell, charge at 1C on balance.
- Re-run compass calibration when you change the airframe layout, and
  accel calibration after any hard landing.
- Watch `logs/mission.log` + `GET /missions/archive` — a slowly rising
  per-mission battery consumption is your earliest warning of a tired
  pack or dragging bearing.

---

## 9. Budget summary

| Tier | Cost | What it gets you |
|---|---|---|
| Simulation only | ₹0 | The full software loop on any PC — this is where all development happens |
| Minimum airframe (§1.1) | ≈ ₹36,000 | A real quad flying real autonomous dispatch missions |
| Recommended (§1.2) | ≈ ₹58,000 | Current-gen autopilot, telemetry radio, sustained test ops |
| + Regulatory | UIN registration fees + insurance as applicable | Legal operation in India under the Drone Rules, 2021 |

The honest advice: spend ₹0 first. Run the SITL stack until you have
dispatched, diverted, recalled, and failsafe-aborted dozens of simulated
missions and can predict what the aircraft will do before it does it.
The hardware then behaves like a faster, windier, more expensive simulator.

---

## 10. The VanniKawachh sensing layer — hub and nodes

Everything in §§1–9 still applies to the drone. This section adds the new
v2 layers. The same ₹0-first advice holds: the entire sensing chain runs in
simulation before you solder anything.

### 10.1 Running the hub in simulation

From the repo root, in the project venv:

```bash
python -m hub.main --sim
```

`--sim` replaces the gateway serial port with synthetic node alerts, so
the full hub pipeline runs on any dev machine: packet unseal (AES-128-CTR +
replay check) → registry lookup → Stage-2 verification (energy-heuristic
fallback if PANNs is not installed) → PIR/LDR/time fusion → dispatch
decision → `POST /trigger`. Point it at a running SITL stack (`run_all.ps1`)
and a simulated distress event flies a simulated drone.

### 10.2 The Phase-0 full-chain demo

```bash
python scripts/demo_phase0.py
```

One command, zero hardware: simulated node alert (WAV or synthesized
scream) → hub pipeline → registry lookup → `POST /trigger` → SITL mission
with hover-record (no-op recorder) and `DELIVERING` (servo command logged
by SITL). This is the architecture proof that precedes any soldering — and
the demo video for the seminar.

### 10.3 Deploying the hub on the Raspberry Pi 5

On Raspberry Pi OS (64-bit), after cloning the repo and creating the venv
as in §4:

```bash
# Stage-2 deep verifier (PANNs) + hub runtime deps
pip install panns-inference torch     # torch CPU build; first PANNs run downloads the checkpoint
pip install pycryptodome pyserial     # AES-128 packet sealing + gateway serial
```

Then:

1. Plug the gateway ESP32 (already flashed per §10.4) into a USB port —
   it appears as `/dev/ttyUSB0`.
2. Create the **node registry** at `hub/nodes.json`: one entry per pole
   with `node_id` and the coordinates you surveyed at install time
   (NEO-6M or a phone — the nodes themselves carry no GPS). Back this
   file up; it is the only mapping from an alert to a place on Earth.
3. Run `python -m hub.main` (no `--sim`) — it reads the gateway serial
   stream and runs the same pipeline as §10.1.

If PANNs/torch are absent the verifier drops to the energy-heuristic
fallback automatically — fine for bench work, not for field deployment.

### 10.4 Flashing the ESP32 sketches

Both sketches live under `firmware/` and build in the **Arduino IDE**:

1. Install the ESP32 board package (Boards Manager → "esp32" by Espressif).
2. Install the libraries: **LoRa by Sandeep Mistry** and **ArduinoJson**
   (Library Manager).
3. `firmware/node/` — select board **ESP32S3 Dev Module**, flash to the
   sensing node (wiring: `HARDWARE_INTEGRATION.md` §§A2–A4).
4. `firmware/gateway/` — select your plain ESP32 dev board, flash to the
   gateway (wiring: `HARDWARE_INTEGRATION.md` §B2), then verify with the
   IDE serial monitor at 115200 baud: each received LoRa packet prints as
   one line.

Bench-test the LoRa link (node on one desk, gateway on another) before any
pole goes up — and never power an SX1278 for TX without its antenna.

---

## 11. Phase 1–4 bring-up order — and the safety rules

Build in this order (details and measured deliverables in
`PROJECT_PLAN.md` §5). Each phase is independently testable; do not start a
phase until the previous one's numbers are recorded.

| Phase | What | Proves |
|---|---|---|
| **1 — Audio bench** (2–3 wks) | ESP32-S3 + INMP441 capturing I2S; Stage-1 TFLM model flashed; clips over WiFi to the Pi 5; PANNs verification | Detection distance vs. SNR, Stage-1 latency (< 50 ms target), Stage-2 latency, false-positive rate on street noise |
| **2 — LoRa alert path** (1–2 wks) | Gateway ESP32 on the Pi's USB; node sends AES-128-sealed alert; hub unseals → registry → pipeline | Range (urban/open), packet loss vs. spreading factor |
| **3 — Drone build + flights** (3–4 wks) | F450 + Pixhawk 2.4.8 + M8N build per §§3–6; manual → GUIDED → full auto in an open private field | The v1 stack on real hardware |
| **4 — Payload + camera + integration** (2 wks) | SG90 release on AUX (`HARDWARE_INTEGRATION.md` §13), Pi Camera Module 3 (§14), then the one-take field demo: scream → node → hub → drone → kit drop | The end-to-end chain |

**Safety rules — non-negotiable at every phase:**

- **VLOS only.** Every prototype flight stays within visual line of sight,
  in an open private field, with the drone registered per the Drone Rules,
  2021. Autonomous BVLOS is a supervised pilot-program pathway on paper,
  not something the prototype flies.
- **RC override in hand.** A trained pilot holds the transmitter with the
  mode switch and kill switch for every flight — the same hardware-level
  override described in §7.
- **Props-off first arming.** Phase 3 starts on the bench with propellers
  removed (§6 step 1); props go on only after motor order and direction
  are verified.
- **Drop tests from ≤ 3 m.** The first-aid kit releases only from a ≤ 3 m
  hover; a failed release means RTL and report — never loiter over people
  troubleshooting a payload.
