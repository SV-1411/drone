# VanniKawachh — Complete System Documentation

This document is the single source of truth for what the system does, how it
is structured, how to run it, how to integrate it, and how to extend it. It
is intended for three kinds of reader:

- A new engineer cloning the repo who needs to be productive in an hour.
- An operations person planning to deploy it on real hardware.
- A reviewer who wants to validate end-to-end behaviour against the spec.

VanniKawachh is a women-safety acoustic intelligence network in three
layers: **sensing nodes** (ESP32-S3, on-device distress detection — §14),
a **hub** (Raspberry Pi 5, verification + fusion + dispatch — §15), and the
**response drone** (the v1 flight stack, preserved unchanged — §§1–13, plus
the v2 additions in §17). The master concept document is
`docs/PROJECT_PLAN.md`.

If you only want to *run* it, skip to §4 "Quickstart" (flight stack) and
`BUILD_AND_OPERATIONS_GUIDE.md` §10 (hub + full chain). If you want to
*fly* it on real hardware, also read `docs/HARDWARE_INTEGRATION.md`.

---

## Table of contents

1. What the system does
2. Use cases
3. Architecture
4. Quickstart
5. Mission lifecycle (sequence)
6. API reference
7. Configuration reference
8. Failsafes
9. Dashboard tour
10. SITL test harness
11. Troubleshooting
12. Extending the system
13. Glossary
14. Sensing node (Stage 1) — NEW in v2
15. Hub service (Stage 2) — NEW in v2
16. Firmware sketches — NEW in v2
17. Flight-core additions: payload release + camera — NEW in v2

---

## 1. What the system does

In VanniKawachh, the trigger is produced by the acoustic chain: a sensing
node hears a distress event (§14), the hub verifies it and looks up the
node's surveyed coordinates (§15), and the hub's dispatcher POSTs
`/trigger` to the flight stack. The flight stack itself is unchanged from
v1 and still accepts any authorized `POST /trigger` — everything in
§§1–13 remains accurate.

A trigger arrives over HTTP carrying a target GPS coordinate. The system:

1. Validates the coordinate.
2. Connects to the autopilot (real or simulated) over MAVLink.
3. Waits for GPS lock and the autopilot's pre-arm checks.
4. **Arms the airframe automatically** — no human input.
5. Takes off to a configured cruise altitude.
6. Navigates to the target in GUIDED mode.
7. Hovers at the target for a configured duration.
8. Returns to launch (RTL) and lands at the home pad.

While that is happening, telemetry (position, altitude, battery, GPS fix,
mission state) streams to a viewer dashboard at 2 Hz over WebSocket. The
operator may *view* the live state and *add* extra waypoints, but the
dashboard exposes no manual flight controls.

If anything goes wrong — battery falls below a threshold, GPS is lost, the
drone crosses the software geofence, the mission takes too long — a
failsafe monitor aborts the current phase and forces RTL or LAND.

The same code drives the simulator (`dronekit-sitl`) and a real
Pixhawk-based airframe. The only difference is the value of one environment
variable (`MAVLINK_CONNECTION`) plus the `SITL_MODE` gate that keeps the
simulation-only pre-arm relaxations turned off on real hardware.

---

## 2. Use cases

The architecture is generic, but four scenarios drove the design.

### 2.1 First-responder dispatch

A 911-style dispatch system triggers the drone with the coordinates of an
incident. The drone arrives ahead of the ground crew, beams live video back
to the command post, and lets the crew assess the scene before they get
there.

Why our system fits: the trigger is a one-shot HTTP POST, there is no human
piloting required, and the dashboard is observation-only.

### 2.2 Perimeter / fence-line inspection

An IoT sensor on a perimeter fence detects a possible breach and triggers a
mission to its location. The drone records imagery, hovers for 30 seconds,
and returns. The incident log on the dashboard becomes an audit trail.

### 2.3 Medical sample / blood-bag relay

A clinic in a remote area triggers a relay to a regional lab, then the lab
triggers a return. Each leg is a separate mission; the priority queue lets
"critical" missions overtake "normal" ones.

### 2.4 Scheduled survey flights

A cron job posts to `/trigger` at a fixed time each day. The aircraft flies
the same waypoint, returns, and uploads its photos. No operator is on duty
at the moment of takeoff.

In each use case, the operator's role is restricted to *authorizing the
trigger source* and *watching the dashboard*. There is no joystick.

---

## 3. Architecture

### 3.1 Component diagram — the full VanniKawachh chain

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
│ Police dashboard (live map + alarm) · alert log            │
└──────────────┬─────────────────────────────────────────────┘
         POST /trigger {lat, lon, incident_type, priority}
               ▼
┌────────────── RESPONSE DRONE (v1 stack, unchanged core) ───┐
│                       HTTP / WebSocket                     │
│   +---------+   +---------------------+  MAVLink  +------+ │
│   |Dashboard|<->|     trigger_api     |<--------->|Ardu- | │
│   | (React) |   |    (FastAPI)        |  (TCP /   |Pilot | │
│   +---------+   +---------------------+   UART)   |SITL/ | │
│                          ^   ^                    |Pixhwk| │
│                          v   v                    +------+ │
│                    +-----------+                           │
│                    |flight_core|  + payload_release (SG90) │
│                    | (Python)  |  + camera_recorder (Pi 3) │
│                    +-----------+                           │
└────────────────────────────────────────────────────────────┘
```

Within the drone layer the v1 boundaries still hold: the dashboard never
speaks MAVLink, the flight core never serves HTTP, and the trigger API owns
both ends and translates between them. The hub is just another API client —
it POSTs `/trigger` exactly as a human or cron job would (§6.1), which is
why the flight stack needed no changes to become the response layer.

### 3.2 Process boundaries

Two processes by default:

- **`trigger_api` process** — runs `uvicorn trigger_api.main:app`. Hosts
  the FastAPI app *and* an in-process `MissionExecutor` from `flight_core`.
  The executor runs on its own thread; the FastAPI request handlers read
  its thread-safe snapshot.
- **`dashboard` process** — runs `vite` in dev mode or a static-server in
  prod. Talks to `trigger_api` over HTTP and WebSocket.

For local SITL there is a third process: `dronekit-sitl` itself, which the
trigger API connects to over TCP.

### 3.3 Thread model inside `trigger_api`

| Thread | Owner | Job |
|---|---|---|
| Main / FastAPI event loop | uvicorn | Serve HTTP + WebSocket |
| MAVLink reader | DroneKit | Drain incoming MAVLink messages, update `Vehicle` |
| Mission queue worker | `mission_queue.py` | Pull the highest-priority queued mission and hand it to the executor |
| Mission executor | `mission_executor.py` | Drive the state machine for the *currently running* mission |
| Telemetry recorder | `mission_executor.py` | Sample the vehicle position every 500 ms and append to the path history |
| Failsafe monitor | `failsafe_handler.py` | Poll vehicle state at 1 Hz and emit failsafe events |

Locks: a single `RLock` on the executor protects the path history, the log
tail, and the pending-extra-waypoints queue. DroneKit's own per-attribute
thread safety handles the live vehicle properties.

### 3.4 Why these technology choices

| Choice | Reason |
|---|---|
| FastAPI | Async + WebSocket support in one library; Pydantic v2 validation; auto-generated Swagger docs |
| DroneKit-Python | Highest-level idiom for ArduPilot — simple `vehicle.simple_takeoff()` calls — even though the project is unmaintained, the API surface is stable enough for production with the 3.10+ shim |
| pymavlink (direct) | Used only as a fallback when DroneKit's mode setter is unreliable on older ArduCopter builds |
| React + Vite | Fast iteration on the viewer; no opinion about the future deployment server |
| Leaflet + OSM | No API key required; map tiles work offline if cached |
| dronekit-sitl | The only ArduCopter SITL distribution that ships prebuilt Windows binaries via pip |

---

## 4. Quickstart

### 4.1 Native (Python + Node, no Docker)

```powershell
git clone https://github.com/SV-1411/drone.git
cd drone
pwsh -File run_all.ps1
```

`run_all.ps1` self-bootstraps Python and Node dependencies, then launches
three windows: SITL, the API, and the dashboard. After ~30 seconds:

- Dashboard at <http://localhost:5173>
- API docs at <http://localhost:8000/docs>
- SITL MAVLink on TCP 127.0.0.1:5760

### 4.2 Docker (any host)

```bash
git clone https://github.com/SV-1411/drone.git && cd drone
docker compose up --build
```

Same three URLs once the containers finish building.

### 4.3 Just the autonomous test

```powershell
cd drone
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python tests\test_full_mission.py
```

Total runtime ≈ 5 minutes. The verdict prints at the end.

### 4.4 Triggering a mission by hand

PowerShell:
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/trigger `
  -ContentType application/json `
  -Body (@{lat=28.6200; lon=77.2150; priority="high"; incident_type="medical"} | ConvertTo-Json)
```

bash/curl:
```bash
curl -X POST http://localhost:8000/trigger \
     -H 'Content-Type: application/json' \
     -d '{"lat":28.6200,"lon":77.2150,"priority":"high","incident_type":"medical"}'
```

Response:
```json
{
  "mission_id": "abc123...",
  "status": "queued",
  "estimated_arrival_s": 132.0,
  "target": [28.62, 77.215]
}
```

Then watch <http://localhost:5173> or poll `GET /telemetry`.

---

## 5. Mission lifecycle

A successful mission walks through these states in order:

```
IDLE
  │     POST /trigger
  ▼
CONNECTING       (lazy — only if not already connected)
  │
  ▼
WAITING_GPS      (block until gps_0.fix_type ≥ 3 and sats ≥ 6)
  │
  ▼
ARMING           (set GUIDED mode; relax pre-arm if SITL_MODE=1;
  │              arm; wait for `vehicle.armed == True`)
  ▼
TAKEOFF          (simple_takeoff(target_alt); wait for alt ≥ 0.95*target)
  │
  ▼
ENROUTE          (simple_goto(target); poll until distance ≤ tolerance)
  │
  ▼  (drain any extra waypoints injected mid-flight)
  │
  ▼
HOVERING         (sleep for hover_s)
  │
  ▼
RTL              (set RTL mode; poll until armed=False and alt<0.5m)
  │
  ▼
LANDED -> COMPLETED
```

**v2 note:** with the payload-release module enabled, a `DELIVERING` phase
(SG90 kit drop via `MAV_CMD_DO_SET_SERVO`) is inserted between `HOVERING`
and `RTL`, and the camera recorder runs across both phases — see §17. The
rest of the lifecycle is unchanged.

If at any point a failsafe fires, the flow jumps to `ABORTED` and the
appropriate action (RTL or LAND) is commanded. If the executor itself
throws, the flow jumps to `FAILED` and a best-effort `safe_rtl()` is
attempted.

### Sequence diagram for a typical successful mission

```
Operator   trigger_api      mission_queue    mission_executor    autopilot
   │            │                  │                  │              │
   │ POST       │                  │                  │              │
   │──/trigger─>│                  │                  │              │
   │            │ enqueue()        │                  │              │
   │            │─────────────────>│                  │              │
   │            │                  │ pop()            │              │
   │            │                  │─────────────────>│              │
   │            │                  │                  │ connect      │
   │            │                  │                  │─────────────>│
   │            │                  │                  │<──── ready ──│
   │            │                  │                  │ set GUIDED   │
   │            │                  │                  │─────────────>│
   │            │                  │                  │ arm          │
   │            │                  │                  │─────────────>│
   │            │                  │                  │ takeoff()    │
   │            │                  │                  │─────────────>│
   │            │                  │                  │  ... climbs  │
   │            │                  │                  │ simple_goto()│
   │            │                  │                  │─────────────>│
   │            │                  │                  │   ...flies   │
   │            │ GET /telemetry   │                  │              │
   │ ←──────────┤                  │ snapshot()       │              │
   │            │─────────────────────────────────────┤              │
   │            │                  │                  │ set RTL      │
   │            │                  │                  │─────────────>│
   │            │                  │                  │  ...lands    │
   │            │                  │ status=done      │              │
   │            │                  │<─────────────────│              │
```

---

## 6. API reference

Base URL (native): `http://localhost:8000`
Swagger UI: `http://localhost:8000/docs`

### 6.1 `POST /trigger`
Dispatch a mission.

**Request body** (Pydantic-validated):
```json
{
  "lat": 28.6200,              // required, -90..90
  "lon": 77.2150,              // required, -180..180
  "priority": "high",          // optional: low|normal|high|critical (default normal)
  "incident_type": "medical",  // optional, free-form (default "generic")
  "altitude_m": 15,            // optional, overrides CRUISE_ALT
  "hover_s": 30                // optional, overrides HOVER_DURATION
}
```

**Response**:
```json
{
  "mission_id": "abc123def456",
  "status": "queued",
  "estimated_arrival_s": 132.0,
  "target": [28.62, 77.215]
}
```

### 6.2 `GET /mission/{mission_id}`
Full mission status (queued | running | done | failed | aborted).

```json
{
  "mission_id": "abc123def456",
  "status": "running",
  "target_lat": 28.62,
  "target_lon": 77.215,
  "altitude_m": 15.0,
  "hover_s": 30,
  "incident_type": "medical",
  "priority": "high",
  "queued_at": 1780723000.0,
  "started_at": 1780723001.5,
  "finished_at": null,
  "final_state": null
}
```

### 6.3 `GET /missions?limit=50`
Recent mission history (newest first). Used by the incident log.

### 6.4 `GET /telemetry`
Current snapshot:
```json
{
  "state": "ENROUTE",
  "mission_id": "abc123def456",
  "lat": 28.6166,
  "lon": 77.2117,
  "alt_m": 15.0,
  "heading_deg": 40.0,
  "ground_speed_ms": 7.99,
  "battery_pct": 84,
  "battery_voltage": 12.5,
  "gps_fix": 3,
  "gps_sats": 10,
  "armed": true,
  "mode": "GUIDED",
  "home_lat": 28.6139,
  "home_lon": 77.2090,
  "target_lat": 28.62,
  "target_lon": 77.215,
  "path": [{"lat":28.61, "lon":77.21, "alt":15.0}, ...],
  "log_tail": ["11:10:55 enroute: dist=891.9m", ...],
  "timestamp": 1780723100.0
}
```

### 6.5 `WS /ws/telemetry`
Same payload as `GET /telemetry`, pushed every `TELEMETRY_INTERVAL_MS` (default 500 ms).

### 6.6 `POST /mission/{mission_id}/waypoint`
Inject an extra waypoint into the currently running mission. The drone
flies there before continuing.

**Request body**:
```json
{ "lat": 28.6180, "lon": 77.2130, "alt": 15.0 }
```

**Response**: `{ "ok": true, "mission_id": "abc123def456" }`

Returns `400` if the named mission isn't in `running` state, or if the
waypoint lies outside the geofence.

### 6.7 `POST /mission/{mission_id}/cancel`
Recall the drone. A `queued` mission is removed from the queue immediately
(`result: "cancelled"`); a `running` mission aborts to RTL
(`result: "aborting"`) and the queue stays blocked until the vehicle has
landed and disarmed.

**Response**: `{ "ok": true, "mission_id": "...", "result": "cancelled" | "aborting" }`

Returns `404` for unknown missions and `400` if the mission already finished.

### 6.8 `GET /missions/archive?limit=200`
Mission history persisted in SQLite (`DB_PATH`), surviving API restarts.
Missions left `queued`/`running` by a crash are reported as `interrupted`.

### 6.9 `GET /health`
Liveness + readiness:
```json
{ "ok": true, "vehicle_connected": true, "state": "IDLE", "queue_depth": 0,
  "auth_enabled": false, "persistence": true }
```

### Authentication

With the `API_TOKEN` env var set, every `POST` endpoint requires the
`X-API-Key` header to match. With it unset (SITL/dev) the API is open —
**never expose an unauthenticated instance beyond localhost.**

---

## 7. Configuration reference

Every knob is an environment variable. Defaults are tuned for SITL.

| Variable | Default | Used by | Notes |
|---|---|---|---|
| `MAVLINK_CONNECTION` | `tcp:127.0.0.1:5760` | flight_core | dronekit connect string. See `docs/HARDWARE_INTEGRATION.md` §4 for real-hardware values |
| `MAVLINK_CONNECT_TIMEOUT` | `90` | flight_core | Per-attempt connect timeout, seconds |
| `MAVLINK_CONNECT_RETRIES` | `5` | flight_core | Retry attempts before giving up |
| `HOME_LAT` / `HOME_LON` | `28.6139` / `77.2090` | flight_core, SITL | Spawn point in SITL; on real hardware, set to your actual pad |
| `HOME_ALT` | `0` (SITL) / `584` (Delhi-elevation default for SITL launchers) | SITL | Elevation in metres above sea level |
| `TARGET_LAT` / `TARGET_LON` | `28.6200` / `77.2150` | flight_core | Used only when the `/trigger` body omits a target |
| `CRUISE_ALT` | `15` | flight_core | Default takeoff/cruise altitude (m) |
| `HOVER_DURATION` | `30` | flight_core | Default seconds to hover at target |
| `WAYPOINT_TOLERANCE` | `5` | flight_core | Distance to target that counts as "arrived" (m) |
| `LOW_BATTERY_PCT` | `20` | failsafe | RTL when battery ≤ this |
| `CRIT_BATTERY_PCT` | `10` | failsafe | LAND when battery ≤ this |
| `GEOFENCE_RADIUS` | `5000` | failsafe | Software fence centered on home (m). On real hardware, also set the ArduPilot `FENCE_*` parameters for hardware-level enforcement |
| `MAX_MISSION_DURATION` | `1800` | failsafe | Mission timeout (s). RTL if exceeded |
| `CRUISE_SPEED` | `8` | flight_core, trigger_api | Ground speed (m/s); also drives the `/trigger` ETA estimate |
| `GPS_BAD_SAMPLES` | `3` | failsafe | Consecutive bad 1 Hz GPS samples before the LAND failsafe fires (debounce) |
| `LEG_STALL_TIMEOUT` | `45` | flight_core | Seconds without progress toward a waypoint before the mission fails safe |
| `LINK_LOSS_TIMEOUT` | `10` | failsafe | Heartbeat age (s) before the stale-telemetry failsafe aborts the mission |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | trigger_api | Bind address for FastAPI |
| `API_TOKEN` | unset | trigger_api | When set, `POST` endpoints require the matching `X-API-Key` header |
| `ALLOWED_ORIGINS` | `*` | trigger_api | Comma-separated CORS origins |
| `MAX_QUEUE_DEPTH` | `20` | trigger_api | Pending-mission cap; beyond it `/trigger` returns HTTP 429 |
| `HISTORY_LIMIT` | `1000` | trigger_api | In-memory mission history cap (finished missions pruned oldest-first) |
| `DB_PATH` | `logs/missions.db` | trigger_api | SQLite mission archive |
| `TELEMETRY_INTERVAL_MS` | `500` | flight_core, trigger_api | Sample cadence for the path history + WebSocket push rate |
| `LOG_DIR` | `logs` | flight_core | Where `mission.log` is written |
| `SITL_MODE` | unset | flight_core | If `1`, the SITL-only pre-arm relaxer runs. **MUST be unset in production.** |

To override per mission, pass `altitude_m` and `hover_s` in the `/trigger`
body.

---

## 8. Failsafes

The failsafe handler runs on its own 1 Hz thread and emits a `FailsafeEvent`
when any of these conditions fire:

| Trigger | Action | Notes |
|---|---|---|
| Battery ≤ `LOW_BATTERY_PCT` | RTL | Fires once; subsequent low readings don't re-trigger |
| Battery ≤ `CRIT_BATTERY_PCT` | LAND | Escalates over a pending RTL — even mid-return |
| GPS `fix_type < 2` for `GPS_BAD_SAMPLES` consecutive samples | LAND | Debounced; a single-sample glitch never lands the aircraft |
| MAVLink heartbeat older than `LINK_LOSS_TIMEOUT` | RTL (attempted) | Stale-telemetry guard: with a dead link every other reading is frozen data; the mission aborts rather than loop on it |
| Distance from home > `GEOFENCE_RADIUS` | RTL | Software fence, secondary to hardware fence. Targets/waypoints outside it are rejected at the API edge |
| Mission running > `MAX_MISSION_DURATION` | RTL | Wall-clock cap |
| No progress toward waypoint for `LEG_STALL_TIMEOUT` s | Mission FAILED → RTL | Catches wind stalls, mode flips, rejected goto commands |
| Operator cancel (`POST /mission/{id}/cancel`) | RTL | The only operator override; still no manual piloting |
| API shutdown with vehicle armed | RTL | The vehicle is sent home before the MAVLink link is dropped |

When an event fires the executor checks it inside every phase loop and at
every phase boundary, then jumps to `ABORTED`. Abort guarantees:

- Abort mode changes use the **confirmed setter** (dronekit attempt + raw
  MAVLink `COMMAND_LONG`/`SET_MODE` fallback) — never the bare dronekit
  setter that older Copter firmware can silently ignore. If the requested
  action won't confirm, the executor tries the alternative (RTL ↔ LAND).
- A LAND demand is never downgraded to RTL.
- The executor **blocks until the vehicle lands and disarms** (capped at
  240 s) before returning, so the queue can never start the next mission
  against an airborne vehicle. As a second line of defence, a new mission
  refuses to start while the vehicle reports armed.

For real-hardware deployments, also configure ArduPilot's own failsafe
parameters (`FS_THR_ENABLE`, `FS_GCS_ENABLE`, `FS_EKF_THRESH`,
`BATT_FS_LOW_ACT`, `BATT_FS_CRT_ACT`, `FENCE_*`) — see
`docs/HARDWARE_INTEGRATION.md` §5.

---

## 9. Dashboard tour

The dashboard is a single React page, divided into a left map and a right
panel.

**Left (map)** — Leaflet over OpenStreetMap tiles. Three markers:
- Green `H` — home base
- Yellow target ring — current mission target
- Blue arrow — live drone position, rotated to the current heading
- Blue polyline — breadcrumb of every position reported since the mission
  began

The map re-centres on the drone after each WebSocket update.

**Right (side panel)** — three sections:
- **Telemetry** — state, mode, armed flag, lat/lon/alt, speed, heading,
  battery %, voltage, GPS fix + satellites
- **Trigger mission** — a form that posts to `/trigger` (the only way the
  operator can issue a mission from the dashboard)
- **Add waypoint** — a form that posts to `/mission/{id}/waypoint`,
  disabled when no mission is running
- **Recent log** — the last 20 log lines from the executor (most recent on top)
- **Incident log** — every mission ever queued, sorted newest first, with
  status badges

There is no joystick, no "manual override", no per-axis control. The
operator is a *viewer*.

---

## 10. SITL test harness

`tests/test_full_mission.py` is a self-contained acceptance test.

What it does:
1. Spawns `dronekit-sitl copter-3.3` as a child process.
2. Waits up to 120 s for TCP 5760 to listen.
3. Spawns `uvicorn trigger_api.main:app` as a child process.
4. Waits up to 60 s for TCP 8000 to listen.
5. Polls `/health` until `vehicle_connected` is `true` (up to 180 s).
6. POSTs `/trigger` with the target coordinate, `altitude_m=15`, `hover_s=5`,
   `priority=high`.
7. Polls `/telemetry` once per second for up to 360 s, recording the maximum
   altitude reached, the minimum distance to target ever observed, and
   whether each phase (RTL, LANDED, COMPLETED) is observed.
8. Tears down the API and SITL subprocesses.
9. Prints a per-check PASS/FAIL summary and an overall verdict.

Run it from the project root:
```powershell
python tests\test_full_mission.py
```

Required env vars: none. The test sets `SITL_MODE=1` internally so the
pre-arm relaxations apply.

Expected total wall-clock: ~321 s (5 min 21 s) on a current laptop.

Expected verdict:
```
============================================================
  PASS  (~321s) — all required checks passed
============================================================
```

If you get a FAIL, see §11.

---

## 11. Troubleshooting

### "Port 5760 already in use"
A previous SITL is still running. Find it and kill it:
```powershell
$p = Get-NetTCPConnection -LocalPort 5760 -State Listen | Select -First 1
if ($p) { Stop-Process -Id $p.OwningProcess -Force }
```

### "vehicle failed to arm"
- In SITL: confirm `SITL_MODE=1` is set in the test env or shell.
- On real hardware: check Mission Planner's pre-arm message. Common culprits:
  bad GPS HDOP, compass calibration not saved, battery voltage below
  `BATT_LOW_VOLT`.

### "failed to enter GUIDED mode"
The raw-MAVLink fallback handles this on ArduCopter 3.3, but if it still
fires:
- Confirm GPS lock is real (`/telemetry` should show `gps_fix=3`, `gps_sats≥6`).
- Confirm the autopilot is fully booted (give SITL 30 s after `Serial port 0 on TCP port 5760`).
- On real Copter 4.x, check that EKF is converged (`vehicle.ekf_ok == True`).

### Test prints "timeout waiting for: vehicle to connect"
The eager-connect at API startup didn't finish in 180 s. The test will
trigger anyway. If this happens routinely, something is wrong with the SITL
boot — read `logs/mission.log` for the most recent connect attempts.

### Dashboard map is grey / no tiles
You're offline and Leaflet can't reach `tile.openstreetmap.org`. Either get
on the internet or cache tiles locally (see Leaflet docs).

### `dronekit-sitl: No such file or directory` on first run
`dronekit-sitl` downloads its prebuilt binary on first run. If your network
blocks GitHub, prefetch it: `dronekit-sitl --list` and then
`dronekit-sitl copter-3.3` once with a connection.

---

## 12. Extending the system

### 12.1 Hardening the authentication layer
API-key auth is built in: set the `API_TOKEN` env var and every `POST`
endpoint requires the matching `X-API-Key` header (see §6). For production,
put nginx with TLS in front of port 8000 so the key is never sent in
clear-text, and set `ALLOWED_ORIGINS` to the dashboard's real origin. For
multi-operator deployments, consider an OIDC integration instead of a
shared key.

### 12.2 Multi-drone support
The current design is single-drone. To support several, refactor
`MissionExecutor` to be keyed by a drone-ID and hold one MAVLink connection
per drone, then route trigger requests by drone-ID or by nearest-available.
The state machine itself doesn't need to change.

### 12.3 Camera / video feed
Add an MJPEG or WebRTC stream from the companion computer's camera and
embed it in the dashboard next to the map. The telemetry contract doesn't
need to change.

### 12.4 Different autopilot
The system uses MAVLink, which PX4 also speaks. Swap DroneKit for direct
pymavlink calls (or `pymavlink.mavwp` / `pymavlink.dialects.v20.common`)
and replace the mode-name strings ("GUIDED" → "OFFBOARD") in the executor.
The trigger API, the queue, the dashboard, and the test harness do not
need to change.

### 12.5 Cloud deployment
Mission history already persists to SQLite (`DB_PATH`, surfaced at
`GET /missions/archive`), so restarts keep the incident record. For a
multi-instance cloud deployment, swap the SQLite store in
`trigger_api/store.py` for PostgreSQL — the `MissionStore` interface
(`upsert` / `load_recent` / `prune`) is the only contract to honour.

---

## 13. Glossary

| Term | Meaning |
|---|---|
| **ArduPilot** | Open-source autopilot firmware family (Copter, Plane, Rover) |
| **Copter 3.3 / 4.x** | Specific ArduCopter releases. SITL on Windows ships 3.3 |
| **dronekit** | Python wrapper around pymavlink, version 2.9.2 used here |
| **dronekit-sitl** | Pip-installable launcher for prebuilt ArduPilot SITL binaries |
| **EKF** | Extended Kalman Filter — ArduPilot's state estimator |
| **Failsafe** | Automatic action taken when a safety condition is violated |
| **Geofence** | Virtual boundary outside of which the drone refuses to fly |
| **GUIDED** | ArduPilot flight mode in which a companion computer drives the drone via MAVLink |
| **HDOP** | Horizontal Dilution Of Precision — GPS quality indicator (lower is better) |
| **MAVLink** | Binary protocol used to talk to ArduPilot / PX4 autopilots |
| **MAVProxy** | Command-line MAVLink ground station |
| **PixHawk** | A family of open-hardware flight controllers that runs ArduPilot |
| **Pre-arm** | The set of safety checks ArduPilot runs before allowing arming |
| **RTL** | Return To Launch — built-in autopilot mode that flies back to the home pad |
| **SITL** | Software-In-The-Loop — autopilot firmware running as a host-OS process |
| **STABILIZE** | ArduPilot manual stabilization mode (the default at boot) |
| **TELEM2** | Secondary UART on a Pixhawk, typically wired to a companion computer |
| **Telemetry** | Continuous low-bandwidth state reports from the aircraft |
| **uvicorn** | ASGI server used to run our FastAPI app |
| **VehicleMode** | DroneKit class representing an ArduPilot flight mode |
| **WPNAV_RADIUS** | ArduPilot parameter — how close counts as "reached" in AUTO mode |

---

## 14. Sensing node (Stage 1) — NEW in v2

One node per pole; hardware in `HARDWARE_INTEGRATION.md` Part A, firmware
in `firmware/node/`. The node's job is a single pipeline that never leaves
the device until something distress-like happens:

```
INMP441 (I2S, 16 kHz mono)
  → framing + MFCC feature extraction
  → tiny CNN (TensorFlow Lite Micro, micro_speech-class)   < 50 ms/frame
  → Stage-1 hit?
       ├─ no  → discard frame (nothing stored, nothing transmitted)
       └─ yes → 1) alert packet over LoRa (AES-128-CTR sealed:
                   node_id, event class, confidence, PIR/LDR flags,
                   monotonic counter)
                2) 4 s audio clip over ESP-NOW/WiFi to the hub
```

Design intent (see `PROJECT_PLAN.md` §3):

- **Recall-tuned.** Stage 1 exists to *not miss* screams / cries /
  "help" / "bachao"-class events. False positives are expected and cheap —
  Stage 2 at the hub filters them.
- **Privacy by construction.** Audio is processed in-place; there is no
  continuous recording or streaming. Only event-triggered clips ≤ 5 s ever
  leave the node, and the alert itself is encrypted.
- **No coordinates on the node.** The alert carries `node_id`; position
  comes from the hub's surveyed registry. A node has no GPS to spoof, jam,
  or drain.
- **LoRa carries the alert, never the audio** (~1–5.5 kbps effective). If
  the WiFi clip never arrives, the hub can still act on multi-node
  corroboration or dispatch at reduced confidence.

---

## 15. Hub service (Stage 2) — NEW in v2

The `hub/` package runs on the Raspberry Pi 5 (or any dev machine in
`--sim` mode — see `BUILD_AND_OPERATIONS_GUIDE.md` §10). One module per
responsibility:

| Module | Responsibility |
|---|---|
| `hub/config.py` | Env-driven hub settings (serial port, keys, thresholds, drone API URL) |
| `hub/node_registry.py` | `node_id → (lat, lon, meta)` registry, JSON-backed (`hub/nodes.json`). Unknown node_id ⇒ packet dropped |
| `hub/packets.py` | LoRa packet format + **AES-128-CTR seal/unseal** with per-node keys and a **monotonic replay counter** — bad MAC or stale counter ⇒ drop (a spoofed packet would launch a drone) |
| `hub/lora_gateway.py` | Reads the gateway ESP32's USB serial stream; `--sim` mode substitutes synthetic packets so the whole pipeline runs with zero hardware |
| `hub/verifier.py` | Stage-2 audio verification: **PANNs** (pretrained AudioSet CNN — CNN14, or CNN10/MobileNet if too slow) when `panns-inference` + `torch` are installed, else an energy-heuristic fallback so the pipeline stays testable |
| `hub/fusion.py` | Severity scoring: PIR motion + darkness (LDR) + time-of-day raise severity of a verified audio event |
| `hub/pipeline.py` | The gate: alert → verify → fuse → dispatch decision. **No dispatch below threshold** — pinned by `tests/test_hub.py` |
| `hub/dispatcher.py` | On a confirmed alert, looks up the node's surveyed coordinates and POSTs `/trigger {lat, lon, incident_type, priority}` to the drone stack (§6.1) |
| `hub/main.py` | Entrypoint: `python -m hub.main` (serial) or `python -m hub.main --sim` |

The two-stage philosophy deliberately mirrors the flight stack's verified
dispatch: Stage 1 is recall-tuned, Stage 2 is precision-tuned — *a
detection claimed is not a detection confirmed*, at every layer.

Tests: `tests/test_hub.py` covers packet seal/unseal + replay rejection,
registry lookup, fusion scoring, pipeline gating, and the dispatcher
payload shape.

---

## 16. Firmware sketches — NEW in v2

Two Arduino sketches under `firmware/` (flash instructions in
`BUILD_AND_OPERATIONS_GUIDE.md` §10.4):

- **`firmware/node/`** — the sensing node (ESP32-S3): I2S mic capture,
  the MFCC + TFLM Stage-1 model hook, PIR/LDR sampling, AES-sealed LoRa
  alert TX, and the ESP-NOW/WiFi clip upload.
- **`firmware/gateway/`** — the hub-side bridge (plain ESP32): LoRa RX →
  one line per packet over USB serial at 115200 baud, consumed by
  `hub/lora_gateway.py`. It does no crypto and no parsing beyond framing —
  all intelligence stays on the Pi where it can be updated without
  reflashing.

Both sketches use *LoRa by Sandeep Mistry* and *ArduinoJson*; wiring
pinouts are in `HARDWARE_INTEGRATION.md` §A4 (node) and §B2 (gateway).

---

## 17. Flight-core additions: payload release + camera — NEW in v2

The v1 flight core — verified mode setter, failsafe arbiter, landing
interlock, geofence, stall detection, obstacle keep-out routing — is
untouched. v2 adds two modules:

### 17.1 `flight_core/payload_release.py` — the DELIVERING phase

Inserts a `DELIVERING` phase between `HOVERING` and `RTL` (§5). It
commands the SG90 release hook through the flight controller with
`MAV_CMD_DO_SET_SERVO` on **servo channel 9** (Pixhawk AUX OUT 1 — wiring
and parameters in `HARDWARE_INTEGRATION.md` §13). Rules enforced:

- Kit drop only from a **≤ 3 m** hover.
- Release failure → **RTL and report**; the drone never loiters on a
  failed drop.
- In SITL the servo command is simply logged by the simulator, so
  `scripts/demo_phase0.py` exercises the full phase with no hardware.

### 17.2 `flight_core/camera_recorder.py` — hover evidence recording

Records from the Pi Camera Module 3 while the mission is in `HOVERING` and
`DELIVERING`, writing an mp4 tagged with the mission id — the evidence
artifact for the incident log. On machines without a camera (SITL, dev
laptops) it is a no-op stub, so the mission flow is byte-identical either
way. Live streaming to police (RTSP/WebRTC) is explicitly future work.
