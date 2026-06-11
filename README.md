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

## Run the tests

```powershell
# fast unit suite — failsafes, queue, validation, persistence (no SITL, ~10s)
pip install -r requirements-dev.txt
python -m pytest

# full end-to-end SITL flight (~5 min)
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
| `GEOFENCE_RADIUS` | `5000` | Metres from home, triggers RTL — targets outside it are rejected at `/trigger` |
| `TELEMETRY_INTERVAL_MS` | `500` | WebSocket push cadence |
| `CRUISE_SPEED` | `8` | Ground speed in m/s (also drives the ETA estimate) |
| `GPS_BAD_SAMPLES` | `3` | Consecutive bad 1 Hz GPS samples before the LAND failsafe fires |
| `LEG_STALL_TIMEOUT` | `45` | Seconds without progress toward a waypoint before the mission fails safe |
| `API_TOKEN` | *(unset)* | When set, `POST` endpoints require the `X-API-Key` header. **Set this in any deployment reachable beyond localhost.** |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins for the API |
| `MAX_QUEUE_DEPTH` | `20` | Pending missions beyond this are rejected with HTTP 429 |
| `DB_PATH` | `logs/missions.db` | SQLite file persisting mission history across restarts |

Override per-mission by passing `altitude_m` and `hover_s` in the `/trigger` body.
Altitude is validated to 2–120 m (the small-UAS AGL ceiling in most jurisdictions).

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

### `POST /mission/{mission_id}/waypoint` — operator-injected extra waypoint (still **no manual flight**).

### `POST /mission/{mission_id}/cancel` — recall the drone. A queued mission is removed; a running mission aborts to RTL and the queue stays blocked until the vehicle is safely down.

### `GET /missions/archive` — mission history persisted in SQLite across API restarts.

> With `API_TOKEN` set, all three `POST` endpoints require the `X-API-Key` header.

## Documentation

- **[`docs/SYSTEM_DOCUMENTATION.md`](docs/SYSTEM_DOCUMENTATION.md)** — complete
  user/operator/developer guide: use cases, architecture, mission lifecycle
  sequence diagram, full API reference, configuration reference, failsafe
  catalogue, dashboard tour, SITL test-harness walkthrough, troubleshooting,
  and extension recipes.
- **[`docs/BUILD_AND_OPERATIONS_GUIDE.md`](docs/BUILD_AND_OPERATIONS_GUIDE.md)**
  — from empty bench to flying system: what to buy (tiered INR budget BOM,
  minimum ≈ ₹36,000), what to download, airframe assembly, companion-computer
  connection, how to run, how missions are commanded/diverted/recalled,
  operating costs.
- **[`docs/HARDWARE_INTEGRATION.md`](docs/HARDWARE_INTEGRATION.md)** — deep
  integration detail: wiring pinouts, calibration, ArduPilot parameter set,
  RC kill-path, bench-to-flight progression, systemd deployment.
- **[`docs/RESEARCH_PAPER.md`](docs/RESEARCH_PAPER.md)** /
  **[`.docx`](docs/RESEARCH_PAPER.docx)** — pre-print: safety-interlocked
  dispatch with verified command delivery; 15 primary-source references,
  embedded original figures, originality + reproducibility statement.
- **[`docs/THESIS.md`](docs/THESIS.md)** / **[`.docx`](docs/THESIS.docx)** —
  print-ready thesis: 9 chapters from motivation through hazard analysis,
  evaluation, hardware realization, and IP analysis, plus appendices.
- **[`docs/patents/`](docs/patents/)** — two draft complete specifications in
  Indian Patent Office Form-2 structure (verified dispatch + failsafe
  arbitration), with prior-art landscape and filing checklist.
- **[`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)** — phased
  roadmap (software modernization → IP filing → hardware → flight validation)
  with budget gates and exit criteria.
- Figures are generated by `python docs/build_diagrams.py`; Word versions by
  `python docs/build_docx.py` (both need `pip install -r requirements-docs.txt`).

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
| Battery ≤ `CRIT_BATTERY_PCT` | LAND (overrides RTL, even mid-return) |
| GPS lost (fix_type < 2) for `GPS_BAD_SAMPLES` consecutive seconds | LAND |
| Distance from home > `GEOFENCE_RADIUS` | RTL |
| Mission running > `MAX_MISSION_DURATION` | RTL |
| No progress toward waypoint for `LEG_STALL_TIMEOUT` s | Mission fails → RTL |
| Operator `POST /mission/{id}/cancel` | RTL |
| API shutdown with vehicle armed | RTL before disconnect |

Failsafe behaviour guarantees: abort commands use the confirmed mode setter
(raw-MAVLink fallback included), a LAND demand is never downgraded to RTL,
an aborted mission blocks the queue until the vehicle has landed and
disarmed, and a new mission refuses to start while the vehicle is armed.

All transitions and failsafe events are written to `logs/mission.log` and
mirrored in the dashboard log tail.
