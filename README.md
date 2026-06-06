# Drone Safety System — Autonomous SITL Demo

An end-to-end autonomous drone navigation system. A trigger arrives → the drone
auto-arms, takes off, flies to the target GPS coordinate, hovers, then
Returns-To-Launch. Operators only **view** telemetry and **optionally** inject
extra waypoints. **No manual piloting.**

```
                   ┌──────────────┐         ┌──────────────┐
   POST /trigger ──▶  trigger_api │  spawns │ flight_core  │
                   │  (FastAPI)   │────────▶│ MissionExec  │
   WS /telemetry ◀─┤              │         │  (dronekit)  │
                   └──────┬───────┘         └──────┬───────┘
                          │                        │ MAVLink
                          ▼                        ▼
                   ┌──────────────┐         ┌──────────────┐
                   │  dashboard   │         │  ArduPilot   │
                   │  (React +    │         │  SITL        │
                   │  Leaflet)    │         │  (sim drone) │
                   └──────────────┘         └──────────────┘
```

## What's in the box

| Path | What it does |
|---|---|
| `flight_core/mission_executor.py` | State machine: connect → GPS lock → arm → takeoff → goto → hover → RTL → land |
| `flight_core/mavlink_interface.py` | Auto-retry MAVLink connect, GPS lock wait, distance maths |
| `flight_core/failsafe_handler.py` | Battery, GPS-loss, geofence, mission-timeout monitors |
| `trigger_api/main.py` | `POST /trigger`, `GET /mission/{id}`, `GET /telemetry`, `WS /ws/telemetry` |
| `trigger_api/mission_queue.py` | Priority queue, single drone, runs missions serially |
| `dashboard/` | React + Vite + Leaflet viewer with live map, telemetry panel, incident log |
| `sitl/start_sitl.{sh,ps1}` | Spawns ArduCopter SITL via `dronekit-sitl` |
| `tests/test_full_mission.py` | Boots SITL+API, dispatches mission, asserts target reached + landed |
| `docker-compose.yml` | Portable full-stack run (SITL + API + dashboard) |
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

Trigger a mission from the dashboard form, or:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/trigger `
  -ContentType application/json `
  -Body (@{lat=28.6200; lon=77.2150; priority="high"; incident_type="medical"} | ConvertTo-Json)
```

## Run the automated end-to-end test

```powershell
python tests\test_full_mission.py
```

What it does:
1. Spawns SITL on port 5760
2. Spawns the FastAPI trigger on port 8000
3. POSTs `/trigger` with `{lat: 28.62, lon: 77.215, alt: 15, hover: 5s}`
4. Polls `/telemetry` and watches the drone arm → takeoff → reach target (±5m) → RTL → land
5. Prints `PASS` or `FAIL` with a checklist

Total runtime ≈ 2–4 minutes depending on SITL boot.

## Quickstart — Docker (optional, portable)

```bash
docker compose up --build
```

Same URLs as native. SITL runs in its own container; the API connects to it
over the docker network at `tcp:sitl:5760`.

## Configuration (env vars)

| Var | Default | Meaning |
|---|---|---|
| `MAVLINK_CONNECTION` | `tcp:127.0.0.1:5760` | dronekit connect string |
| `HOME_LAT` / `HOME_LON` | `28.6139 / 77.2090` | Spawn coordinates (also the RTL point) |
| `TARGET_LAT` / `TARGET_LON` | `28.6200 / 77.2150` | Default target if not in the trigger body |
| `CRUISE_ALT` | `15` | Takeoff / cruise altitude in metres |
| `HOVER_DURATION` | `30` | Seconds to hover at target before RTL |
| `WAYPOINT_TOLERANCE` | `5` | Metres — counts as "arrived" |
| `LOW_BATTERY_PCT` | `20` | Triggers RTL |
| `CRIT_BATTERY_PCT` | `10` | Triggers LAND |
| `GEOFENCE_RADIUS` | `5000` | Metres from home, triggers RTL |
| `TELEMETRY_INTERVAL_MS` | `500` | WebSocket push cadence |

Override per-mission by passing `altitude_m` and `hover_s` in the `/trigger` body.

## API

### `POST /trigger`
```json
{ "lat": 28.62, "lon": 77.215, "priority": "high", "incident_type": "medical",
  "altitude_m": 15, "hover_s": 30 }
```
Returns `{"mission_id": "...", "status": "queued", "estimated_arrival_s": 87.2, "target": [lat, lon]}`.

### `GET /mission/{mission_id}` — full mission status (queued / running / done / failed / aborted).

### `GET /telemetry` — current drone state, path, recent log lines.

### `WS /ws/telemetry` — same payload pushed every `TELEMETRY_INTERVAL_MS`.

### `POST /mission/{mission_id}/waypoint` — operator-injected extra waypoint (the only operator action; still **no manual flight**).

## Moving to real hardware

This SITL build is a complete, working stand-in for the autonomous flight
stack. To put it on a real aircraft (Pixhawk + ArduCopter + RPi companion
computer), see **[`docs/HARDWARE_INTEGRATION.md`](docs/HARDWARE_INTEGRATION.md)**.
That guide covers BOM, wiring, calibration, the ArduPilot parameter set you
must apply for real flight, the mandatory RC kill path, the recommended
bench → tethered → autonomous flight progression, and a production systemd
deployment.

> **Important**: the SITL code disables ArduPilot pre-arm checks
> (`ARMING_CHECK=0`) so the simulated drone can arm without an RC stream.
> That relaxation is gated behind the `SITL_MODE=1` env var — leave it unset
> on real hardware so full pre-arm safety is in force.

## Notes on Python 3.10+ & dronekit

`dronekit==2.9.2` predates Python 3.10 and imports `collections.MutableMapping`,
which was removed in 3.10. `flight_core/mavlink_interface.py` re-aliases the
abc symbols back onto `collections` *before* importing dronekit, so the
high-level Vehicle API still works on 3.11 / 3.12.

## Failsafes

| Trigger | Action |
|---|---|
| Battery ≤ `LOW_BATTERY_PCT` | RTL |
| Battery ≤ `CRIT_BATTERY_PCT` | LAND |
| GPS lost (fix_type < 2) | LAND |
| Distance from home > `GEOFENCE_RADIUS` | RTL |
| Mission running > `MAX_MISSION_DURATION` | RTL |

All transitions and failsafe events are written to `logs/mission.log` and
mirrored in the dashboard log tail.
