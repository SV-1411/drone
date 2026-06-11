# CLAUDE.md — Project context for AI-assisted sessions

This file is the orientation document for anyone (human or AI assistant)
picking up this repository. It records what the project is, how it got
here, what decisions were made and why, and what's next. Keep it updated
when major work lands.

## What this project is

**Drone Safety System** — a trigger-driven autonomous UAV dispatch stack.
An HTTP request carrying a GPS coordinate causes a drone to auto-arm,
take off, fly to the target, hover, return, and land — **zero manual
piloting**. Operators can only view telemetry, inject optional waypoints,
or recall (cancel) the mission. Validated end-to-end in ArduPilot SITL;
designed to move to a real Pixhawk + Raspberry Pi airframe by changing
one environment variable.

- Repo: https://github.com/SV-1411/drone.git (public)
- Local working copy: `D:\drone-safety-system` (Windows 11 dev machine)
- Python venv: `.venv\` (Python 3.11; activate before running anything)

## Architecture (30 seconds)

```
Dashboard (React+Leaflet) <--HTTP/WS--> trigger_api (FastAPI) <--in-process--> flight_core
                                                                                   |
                                                                          MAVLink (TCP or UART)
                                                                                   |
                                                                  ArduPilot SITL  or  Pixhawk
```

- `flight_core/` — mission executor (12-state machine), MAVLink interface
  (+ Python 3.10+ shim for dronekit), failsafe arbiter, env-driven config.
- `trigger_api/` — FastAPI app: `/trigger`, `/mission/{id}`,
  `/mission/{id}/cancel`, `/mission/{id}/waypoint`, `/missions[/archive]`,
  `/telemetry`, WS `/ws/telemetry`, `/health`. Priority queue + SQLite
  persistence (`trigger_api/store.py`).
- `dashboard/` — React 18 + Vite + Leaflet viewer (no flight controls).
- `tests/` — `test_units.py` (37 pytest cases, ~15 s, no SITL) and
  `test_full_mission.py` (end-to-end SITL flight, ~5–6 min, standalone
  script not pytest).
- `docs/` — full documentation set (see below).

## The safety design (the heart of the project)

Three mechanisms distinguish this from a naive "send drone to GPS" script.
Understand these before touching `mission_executor.py` or
`failsafe_handler.py`:

1. **Verified mode transition** (`_set_mode_confirmed` /
   `_raw_set_mode`): every flight-mode change — including emergency
   RTL/LAND — is issued via dronekit, then re-issued every 700 ms as raw
   MAVLink `COMMAND_LONG(MAV_CMD_DO_SET_MODE)` + `SET_MODE` until the
   autopilot's HEARTBEAT-reported mode confirms it. Reason: ArduCopter
   3.3 SITL **silently ignores** dronekit's plain mode setter (client
   says GUIDED, autopilot stays STABILIZE). On the abort path there's a
   cross-fallback: unconfirmable RTL → try LAND, and vice versa.
   **Never use `vehicle.mode = ...` directly anywhere.**

2. **Landing interlock**: every abort path blocks until the vehicle
   lands AND disarms (≤240 s) before the queue regains control, and
   `run_mission` refuses to start while the vehicle is armed. Invariant:
   *the queue can never start a flight against an airborne vehicle.*
   Shutdown with an armed vehicle commands RTL before disconnecting.

3. **Failsafe arbitration** (`failsafe_handler.py`): LAND ≻ RTL, never
   downgraded; GPS loss debounced (3 consecutive bad 1 Hz samples, reset
   on recovery) and demands LAND (no GPS = no navigable return); each
   named failsafe fires once per mission (re-fire only to escalate);
   the RTL phase loop re-checks the arbiter and switches to LAND
   mid-return on escalation. Plus: per-leg stall detector (no progress
   45 s → mission fails to RTL), geofence targets rejected at the API
   edge, altitude bounded 2–120 m.

## How to run / test

```powershell
cd D:\drone-safety-system; .\.venv\Scripts\Activate.ps1
python -m pytest                       # unit tier, 37 cases, ~15 s
python tests\test_full_mission.py      # SITL e2e flight, ~5-6 min, prints PASS/FAIL
.\run_all.ps1                          # live stack: SITL + API + dashboard windows
python docs\build_diagrams.py          # regenerate the 8 figures (needs requirements-docs.txt)
python docs\build_docx.py              # regenerate paper/thesis .docx from markdown
```

Docker (`docker compose up --build`) exists but has **never been run** on
this machine (no Docker Desktop) — it was repaired by review (healthcheck
gating, `API_UPSTREAM` proxy) but is unverified.

## Critical gotchas (learned the hard way)

- **dronekit 2.9.2 is unmaintained**: needs the `collections` ABC shim in
  `mavlink_interface.py` (runs BEFORE `import dronekit`) and the `future`
  package. Migration to pymavlink is the top roadmap item.
- **`copter-3.3` is the only dronekit-sitl build that works on Windows**
  — plain `copter` fails. The test, `run_all.ps1`, and `start_sitl.sh`
  are all pinned to it.
- **`SITL_MODE=1`** gates the pre-arm relaxer (`ARMING_CHECK=0` etc.).
  Set in SITL contexts only; **must stay unset on real hardware**.
- **Config reads env at construction** (`Config.from_env()` →
  module-level `CONFIG`). Set env vars before process start.
- **`is_armable` is unreliable on Copter 3.3** — the executor proceeds
  after a 45 s wait and lets the explicit arm-confirm raise instead.
  Don't "fix" this by raising on the armable timeout.
- **`pytest.ini` pins testpaths** — running pytest from outside the repo
  root hits a Windows permissions crash (`D:\WpSystem`).
- **`context1.docs` is gitignored on purpose** — it's a session
  transcript containing personal info; never commit it.
- The e2e test takes ~5–6 min and spawns SITL + uvicorn as children;
  run it in the background and poll, don't block.

## Documentation map (`docs/`)

| File | Purpose |
|---|---|
| `SYSTEM_DOCUMENTATION.md` | Operator/developer reference (API, config, failsafes, troubleshooting) |
| `BUILD_AND_OPERATIONS_GUIDE.md` | Shopping list (min ≈ ₹36k INR BOM), assembly, connection, ops |
| `HARDWARE_INTEGRATION.md` | Wiring pinouts, ArduPilot params, calibration, SITL→hardware switch |
| `RESEARCH_PAPER.md` / `.docx` | Pre-print (v2): safety-interlocked dispatch w/ verified command delivery |
| `THESIS.md` / `.docx` | 9-chapter print-ready thesis |
| `patents/` | Two IPO Form-2 draft specs + prior-art landscape + filing checklist |
| `IMPLEMENTATION_PLAN.md` | Phased roadmap with budget gates |
| `build_diagrams.py` | Generates all 8 figures (matplotlib, original) |
| `build_docx.py` | Generic md→docx renderer (cover, tables, figures, page numbers) |
| `figures/` | Generated PNGs (committed) |

## Session history

**Session 1 (2026-06-06) — initial build.** Full stack built from a spec
prompt; three SITL bugs found and fixed (dronekit/Py3.11 shim + `future`
pkg; SITL arming relaxation; the silent GUIDED rejection → raw-MAVLink
fallback). 5 consecutive e2e PASSes. Pushed to GitHub. Hardware guide,
research paper v1, system documentation, Word build script, 5 figures.

**Session 2 (2026-06-11) — deep review + deep fix.** Full-code review
found 5 critical / 7 high / 9 medium issues. All fixed (commit
`6187104`): abort paths moved to the confirmed setter; landing
interlock added; GPS debounce; cancel endpoint + dashboard button;
API-token auth; geofence/altitude edge validation; queue caps + SQLite
persistence; eager-connect off the event loop; Docker repair
(healthcheck, `API_UPSTREAM`); `run_all.ps1` pinned to copter-3.3;
dashboard offline assets + follow toggle; requirements split
(runtime/dev/docs); 37-case unit suite added. Verified: 37/37 + e2e
PASS (331.3 s, 0.6 m closest approach, 8/8 required checks).

**Session 3 (2026-06-11/12) — docs & IP package** (commit `a6a4798`).
Research paper rewritten (v2) around the safety contributions; thesis
written; build & ops guide with INR budget; patent landscape scanned
(US10216181B2, US10089889B2, US12184803B2, delivery families — raw
"trigger→GPS dispatch" is NOT novel; the verification/interlock layer
is the claimable part); two IPO Form-2 patent drafts; 3 new figures;
generic docx pipeline (replaced `build_paper.py`); implementation plan.

## Current state & what's next

**Done:** Phases 0–1 of `docs/IMPLEMENTATION_PLAN.md` (validated
software + full docs/IP package). All tests green at last commit.

**Next (in order):**
1. GitHub Actions CI running pytest (quick win).
2. Migrate dronekit → pymavlink/MAVSDK; validate on ArduPilot 4.x SITL
   (Docker/WSL2). Only `mavlink_interface.py` + parts of the executor
   should change.
3. Fault-injection e2e scenarios (battery collapse, GPS denial, fence
   breach mid-flight).
4. Patent filing (user action: novelty search + registered agent —
   urgent because the public repo is self-disclosure).
5. Hardware build per `BUILD_AND_OPERATIONS_GUIDE.md`, then staged
   flight tests.

**Open caveats:** Docker path unverified; plagiarism scores not yet run
through Turnitin (user action); author placeholders in paper/thesis/
patents still say *(to be filled in)*.

## Conventions for future sessions

- Safety-relevant changes (executor, failsafe, queue) get a unit test in
  `tests/test_units.py` before they're considered done.
- After touching flight logic, run the unit tier always; run the e2e
  flight before any push that changes `flight_core/`.
- Edit `.md` sources and regenerate `.docx` via `docs/build_docx.py` —
  never edit the `.docx` directly.
- Commit messages: imperative summary + bulleted detail; push to `main`
  on https://github.com/SV-1411/drone.git after verification.
