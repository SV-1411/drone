# VanniKawachh — Acoustic Intelligence + Autonomous Drone Response for Women Safety

Solar-powered microphone nodes on poles in high-risk public spots (dark
streets, forest stretches, campus outskirts, parking areas) listen 24×7. Each
node's ESP32-S3 screens every audio frame on-device with a lightweight
MFCC + CNN model (Stage 1, < 50 ms, high recall). Distress-like events are
verified at a Raspberry Pi 5 hub running PANNs deep audio analysis fused with
PIR motion, LDR light and time-of-day evidence (Stage 2, high precision). A
confirmed alert — AES-128-encrypted, carrying the node's surveyed GPS
coordinates — travels over LoRa (no SIM, no cellular) to the police dashboard
and simultaneously auto-dispatches a Pixhawk quadcopter that flies to the
spot, records camera evidence, and drops a first-aid kit. The victim needs no
phone, no app, no wearable — **her voice is the trigger**.

Repo: <https://github.com/SV-1411/drone> · Master plan: [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)

> The autonomous flight stack (below the `POST /trigger` line) is the
> SITL-verified v1 "Drone Safety System" — it is now the **response layer**
> of VanniKawachh, with a camera recorder and payload-drop state added on top.

```
┌────────────── SENSING NODE (per pole, solar) ──────────────┐
│ INMP441 I2S mic → ESP32-S3: MFCC + tiny CNN (TFLM, <50 ms) │
│ PIR (HC-SR501) + LDR context · Stage-1 hit → alert + clip  │
└──────────────┬─────────────────────────────┬───────────────┘
        LoRa SX1278 (alert, AES-128)   ESP-NOW / WiFi (4 s audio clip)
               ▼                             ▼
┌────────────── HUB (Raspberry Pi 5, per locality) ──────────┐
│ LoRa gateway (ESP32 + SX1278 on USB serial)                │
│ Stage 2: PANNs (CNN14/CNN10) + PIR/LDR/time fusion score   │
│ Node registry: node_id → surveyed (lat, lon)               │
└──────────────┬─────────────────────────────────────────────┘
         POST /trigger {lat, lon, incident_type, priority}
               ▼
┌────────────── RESPONSE DRONE (v1 stack, unchanged core) ───┐
│ trigger_api (FastAPI queue) → mission_executor (12-state   │
│ FSM, verified mode setter, failsafe arbiter, landing       │
│ interlock) · HOVER+record (camera) → DELIVERING (SG90      │
│ first-aid drop) → RTL                                      │
└────────────────────────────────────────────────────────────┘
```

## What's in the box

| Path | What it does |
|---|---|
| `hub/` | Stage-2 hub service: LoRa gateway reader (`--sim` mode), AES-128 packet seal/unseal, node registry, PANNs/heuristic verifier, PIR/LDR/time fusion, dispatch pipeline |
| `firmware/node/` | ESP32-S3 sensing-node sketch (I2S mic, MFCC+TFLM hook, PIR/LDR, LoRa TX, clip upload) |
| `firmware/gateway/` | Hub-side ESP32 LoRa RX → USB serial bridge |
| `flight_core/mission_executor.py` | State machine: connect → GPS lock → arm → takeoff → goto → hover/record → deliver → RTL → land |
| `flight_core/camera_recorder.py` | Evidence recording during hover (mp4 tagged with mission id; no-op in SITL) |
| `flight_core/payload_release.py` | SG90 first-aid-kit release via `MAV_CMD_DO_SET_SERVO` |
| `flight_core/failsafe_handler.py` | Battery, GPS-loss, geofence, link-loss, stall, mission-timeout monitors |
| `trigger_api/main.py` | `POST /trigger`, `GET /mission/{id}`, `GET /telemetry`, `WS /ws/telemetry` |
| `dashboard/` | React + Vite + Leaflet viewer with live map, telemetry panel, incident log |
| `scripts/demo_phase0.py` | Full-chain SITL demo: simulated scream → hub → dispatch → flight (zero hardware) |
| `sitl/start_sitl.{sh,ps1}` | Spawns ArduCopter SITL via `dronekit-sitl` |
| `tests/` | Unit tier (`test_units.py`, `test_hub.py`, `test_obstacle_avoidance.py`) + e2e `test_full_mission.py` |
| `run_all.ps1` | One-command native launcher (Windows) |

## Prerequisites

- Python 3.10+ (tested on 3.11)
- Node 18+ / npm
- (Optional) Docker Desktop, only if you want the container path

## Quickstart — native (no Docker)

From the project root (`D:\drone-safety-system`):

```powershell
# install Python + Node deps and launch SITL, API, dashboard in three windows
.\run_all.ps1
```

Then open:
- Dashboard: <http://localhost:5173>
- API docs:  <http://localhost:8000/docs>

### Full-chain demo (Phase 0 — sensing sim → hub → drone, zero hardware)

```powershell
python scripts\demo_phase0.py
```

Simulates a node distress alert, runs the hub pipeline (fallback verifier if
PANNs is not installed), resolves the node's coordinates from the registry,
POSTs `/trigger`, and the SITL drone flies the mission with hover-record and
the DELIVERING (servo) state.

### Run the hub on its own

```powershell
python -m hub.main --sim     # simulated LoRa gateway (no serial hardware)
```

On the real Pi 5 hub, drop `--sim` and point it at the gateway ESP32's serial
port (see `hub/config.py` for env vars).

### Trigger the drone directly

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/trigger `
  -ContentType application/json `
  -Body (@{lat=28.6200; lon=77.2150; priority="high"; incident_type="distress"} | ConvertTo-Json)
```

## Run the tests

```powershell
# fast unit suite — failsafes, queue, validators, hub packets/registry/fusion (no SITL)
pip install -r requirements-dev.txt
python -m pytest

# full end-to-end SITL flight (~5 min)
python tests\test_full_mission.py
```

The e2e script spawns SITL on 5760 and the API on 8000, POSTs `/trigger`,
then watches the drone arm → takeoff → reach target (±5 m) → RTL → land and
prints `PASS`/`FAIL` with a checklist.

## Quickstart — Docker (optional, portable)

```bash
docker compose up --build
```

Same URLs as native. SITL runs in its own container; the API connects to it
over the docker network at `tcp:sitl:5760`.

## Configuration (drone stack env vars — most used)

| Var | Default | Meaning |
|---|---|---|
| `MAVLINK_CONNECTION` | `tcp:127.0.0.1:5760` | dronekit connect string |
| `HOME_LAT` / `HOME_LON` | `28.6139 / 77.2090` | Spawn coordinates (also the RTL point) |
| `CRUISE_ALT` | `15` | Takeoff / cruise altitude in metres |
| `HOVER_DURATION` | `30` | Seconds to hover (and record) at target before RTL |
| `GEOFENCE_RADIUS` | `5000` | Metres from home — targets outside are rejected at `/trigger` |
| `API_TOKEN` | *(unset)* | When set, `POST` endpoints require the `X-API-Key` header |

The full table (failsafe thresholds, queue caps, persistence, CORS) is in
[`docs/SYSTEM_DOCUMENTATION.md`](docs/SYSTEM_DOCUMENTATION.md); hub settings
live in `hub/config.py`.

## Documentation

- **[`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)** — the v2 master plan:
  concept, research grounding, architecture, phases, BOM, safety/privacy/legal.
- **[`docs/SYSTEM_DOCUMENTATION.md`](docs/SYSTEM_DOCUMENTATION.md)** — flight
  stack operator/developer guide (API, config, failsafes, troubleshooting).
- **[`docs/BUILD_AND_OPERATIONS_GUIDE.md`](docs/BUILD_AND_OPERATIONS_GUIDE.md)**
  / **[`docs/HARDWARE_INTEGRATION.md`](docs/HARDWARE_INTEGRATION.md)** — drone
  hardware BOM, wiring, calibration, ArduPilot params, bench→flight progression.
- **[`docs/RESEARCH_PAPER.md`](docs/RESEARCH_PAPER.md)** /
  **[`docs/THESIS.md`](docs/THESIS.md)** / **[`docs/patents/`](docs/patents/)**
  — v1 flight-stack pre-print, thesis, and two IPO Form-2 patent drafts
  (verified dispatch + failsafe arbitration). These describe the flight stack,
  which is unchanged in v2.
- **[`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)** — v1 roadmap
  history + pointer to the v2 phase plan.

## Failsafes (response drone)

| Trigger | Action |
|---|---|
| Battery ≤ `LOW_BATTERY_PCT` | RTL |
| Battery ≤ `CRIT_BATTERY_PCT` | LAND (overrides RTL, even mid-return) |
| GPS lost for `GPS_BAD_SAMPLES` consecutive seconds | LAND |
| MAVLink heartbeat silent for `LINK_LOSS_TIMEOUT` s | Abort → RTL attempt |
| Distance from home > `GEOFENCE_RADIUS` | RTL |
| No progress toward waypoint for `LEG_STALL_TIMEOUT` s | Mission fails → RTL |
| Payload release failure | RTL and report (never loiter on a failed drop) |
| Operator `POST /mission/{id}/cancel` | RTL |

Abort commands use the confirmed mode setter (raw-MAVLink fallback included),
a LAND demand is never downgraded to RTL, and an aborted mission blocks the
queue until the vehicle has landed and disarmed.

## Safety, privacy, legal

- **Privacy:** no continuous recording or transmission — audio is processed
  on-device; only event-triggered clips ≤ 5 s leave a node, encrypted.
- **Spoofing:** every LoRa packet is AES-128 sealed with per-node keys and a
  monotonic counter; unknown node_id or bad MAC ⇒ dropped (a spoofed packet
  would launch a drone).
- **Flight law:** prototype flights are VLOS in an open private field with an
  RC override in hand, drone registered per Drone Rules 2021. SITL runs with
  `SITL_MODE=1` (pre-arm relaxation) — **leave it unset on real hardware**.
