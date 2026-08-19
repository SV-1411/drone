# CLAUDE.md — Project context for AI-assisted sessions

This file is the orientation document for anyone (human or AI assistant)
picking up this repository. It records what the project is, how it got
here, what decisions were made and why, and what's next. Keep it updated
when major work lands.

## What this project is

**VanniKawachh** — a distributed AI acoustic intelligence and autonomous
drone response network for women safety (concept pivot 2026-07-06; master
plan: `docs/PROJECT_PLAN.md`). Solar-powered ESP32-S3 + INMP441 nodes on
poles do on-device MFCC+CNN distress detection (Stage 1); a Raspberry Pi 5
hub verifies with PANNs + PIR/LDR/time sensor fusion (Stage 2), sends
AES-128-encrypted alerts with the node's surveyed coordinates over LoRa
SX1278 (no internet), and auto-dispatches the drone stack.

The v1 "Drone Safety System" — the trigger-driven autonomous UAV dispatch
stack (HTTP trigger → auto-arm → takeoff → goto → hover → RTL, **zero
manual piloting**, validated end-to-end in ArduPilot SITL) — is now the
**response layer** of VanniKawachh. Its core is **unchanged**; v2 adds
hover-time camera evidence recording and an SG90 first-aid-kit drop on top.
The v1 docs, patents, and papers describe this flight stack and remain
accurate for it.

- Repo: https://github.com/SV-1411/drone.git (public)
- Local working copy: `D:\drone-safety-system` (Windows 11 dev machine;
  since 2026-08-19 this is a NEW machine — 16 GB RAM, RTX 3050 6 GB — the
  old 8 GB DELL is gone)
- Python venv: `.venv\` (Python 3.13 on this machine; activate before
  running anything)

## Architecture (30 seconds)

```
Sensing node (ESP32-S3: MFCC+TFLM CNN, PIR, LDR)
   | LoRa SX1278 (AES-128 alert)     | ESP-NOW/WiFi (4 s clip)
   ▼                                 ▼
Hub (Pi 5): lora_gateway → verifier (PANNs) → fusion → pipeline → dispatcher
   | POST /trigger {lat, lon, incident_type, priority}
   ▼
Dashboard (React+Leaflet) <--HTTP/WS--> trigger_api (FastAPI) <--in-process--> flight_core
                                                                                   |
                                                                          MAVLink (TCP or UART)
                                                                                   |
                                                                  ArduPilot SITL  or  Pixhawk
```

- `flight_core/` — mission executor (12-state machine), MAVLink interface
  (+ Python 3.10+ shim for dronekit), failsafe arbiter, env-driven config.
  NEW in v2: `payload_release.py` (SG90 drop via `MAV_CMD_DO_SET_SERVO`)
  and `camera_recorder.py` (evidence mp4 during hover; no-op in SITL).
- `trigger_api/` — FastAPI app: `/trigger`, `/mission/{id}`,
  `/mission/{id}/cancel`, `/mission/{id}/waypoint`, `/missions[/archive]`,
  `/telemetry`, WS `/ws/telemetry`, `/health`. Priority queue + SQLite
  persistence (`trigger_api/store.py`). API unchanged in v2 — the hub is
  just another client of `/trigger`.
- `hub/` — NEW: Stage-2 hub service (Pi 5). `config.py`, `node_registry.py`
  (node_id → lat/lon), `packets.py` (LoRa format + AES-128 seal/unseal),
  `lora_gateway.py` (serial reader, `--sim` mode), `verifier.py` (PANNs or
  energy-heuristic fallback), `fusion.py` (PIR/LDR/time severity),
  `pipeline.py`, `dispatcher.py`, `main.py` (`python -m hub.main --sim`).
- `firmware/` — NEW: ESP32 sketches — `node/` (sensing node) and
  `gateway/` (hub-side LoRa RX → USB serial bridge).
- `scripts/demo_phase0.py` — NEW: full-chain SITL demo (simulated scream →
  hub pipeline → dispatch → flight), zero hardware.
- `dashboard/` — React 18 + Vite + Leaflet viewer (no flight controls).
- `tests/` — `test_units.py` (pytest, no SITL), `test_hub.py` (NEW: packet
  seal/unseal + replay, registry, fusion, pipeline gating, dispatcher),
  `test_obstacle_avoidance.py`, and `test_full_mission.py` (end-to-end
  SITL flight, ~5–6 min, standalone script not pytest).
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
python -m pytest                       # unit tier (incl. test_hub.py), no SITL
python tests\test_full_mission.py      # SITL e2e flight, ~5-6 min, prints PASS/FAIL
.\run_all.ps1                          # live stack: SITL + API + dashboard windows
python scripts\demo_phase0.py          # NEW: full-chain demo (sensing sim → hub → flight)
python -m hub.main --sim               # NEW: hub alone, simulated LoRa gateway
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
| `PROJECT_PLAN.md` | **v2 master plan** — VanniKawachh concept, architecture, phases, BOM, safety/privacy/legal |
| `SYSTEM_DOCUMENTATION.md` | Flight-stack operator/developer reference (API, config, failsafes, troubleshooting) |
| `BUILD_AND_OPERATIONS_GUIDE.md` | Drone shopping list (min ≈ ₹36k INR BOM), assembly, connection, ops |
| `HARDWARE_INTEGRATION.md` | Wiring pinouts, ArduPilot params, calibration, SITL→hardware switch |
| `RESEARCH_PAPER.md` / `.docx` | Pre-print: safety-interlocked dispatch w/ verified command delivery (flight stack — unchanged in v2) |
| `THESIS.md` / `.docx` | 9-chapter print-ready thesis (flight stack — unchanged in v2) |
| `patents/` | Two IPO Form-2 draft specs + prior-art landscape + filing checklist (flight stack — unchanged in v2) |
| `IMPLEMENTATION_PLAN.md` | v1 roadmap history + pointer to the v2 phase plan in `PROJECT_PLAN.md` |
| `build_diagrams.py` | Generates all 8 figures (matplotlib, original) |
| `build_docx.py` | Generic md→docx renderer (cover, tables, figures, page numbers) |
| `figures/` | Generated PNGs (committed) |

> **Note on v1 documents:** `RESEARCH_PAPER.md`, `THESIS.md`, and everything
> under `patents/` were written for the v1 flight stack. That stack is
> unchanged in v2, so those documents remain accurate for what they cover —
> do not rewrite them for the pivot; new sensing-layer papers are separate
> deliverables per `PROJECT_PLAN.md`.

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

**Session 3a (2026-06-12) — residual-flaw pass.** Fresh review of the
hardened code found 5 residual flaws, all fixed: link-loss/stale-telemetry
failsafe (`LINK_LOSS_TIMEOUT`, heartbeat-age check in the arbiter);
dashboard API-token field (writes were 401-ing whenever `API_TOKEN` was
set); direct unit tests for the verified setter + abort interlock via a
`ModeRejectingVehicle` mock (suite now 47 cases); loud warning when
battery telemetry is absent; `run_all.ps1` now uses the venv interpreter.

**Session 3 (2026-06-11/12) — docs & IP package** (commit `a6a4798`).
Research paper rewritten (v2) around the safety contributions; thesis
written; build & ops guide with INR budget; patent landscape scanned
(US10216181B2, US10089889B2, US12184803B2, delivery families — raw
"trigger→GPS dispatch" is NOT novel; the verification/interlock layer
is the claimable part); two IPO Form-2 patent drafts; 3 new figures;
generic docx pipeline (replaced `build_paper.py`); implementation plan.

**Session 4 (2026-07-06) — concept pivot to VanniKawachh.** The project
is reframed as a women-safety acoustic intelligence network (GHRCE group
project, CSE_B_04): ESP32-S3+INMP441 nodes (Stage-1 MFCC+CNN on-device)
→ Pi 5 hub (Stage-2 PANNs + PIR/LDR/time fusion) → AES-128 LoRa alerts
→ the existing drone stack as the response layer, extended with camera
evidence recording and an SG90 first-aid drop. Decision: **the v1 flight
core is untouched** — all safety machinery (verified setter, failsafe
arbiter, landing interlock, geofence, stall detection) carries over
verbatim, and the v1 paper/thesis/patents still describe it accurately.
New code: `hub/` package, `firmware/` sketches, `scripts/demo_phase0.py`,
`flight_core/payload_release.py`, `flight_core/camera_recorder.py`,
`tests/test_hub.py`. Master plan: `docs/PROJECT_PLAN.md` (supersedes
`IMPLEMENTATION_PLAN.md`, which now points there). README/CLAUDE.md/
IMPLEMENTATION_PLAN.md updated for the pivot.

**Session 5 (2026-08-19) — new machine + real AudioSet detectors.** Repo
recloned on the new dev machine (16 GB RAM / RTX 3050; `.venv` is Python
3.13, TF 2.21, CPU torch). The real-model upgrade the previous session
planned is done: `hub/yamnet_detector.py` runs the full YAMNet TFLite
export (committed at `hub/models/yamnet.tflite` + class map) and is now
the live decider in `hub/webapp.py:stage1_phone` (DSP `scream_dsp.py`
remains the fallback where no TFLite runtime exists, e.g. free Render).
`hub/verifier.py` Stage-2 chain is now PANNs → YAMNet → energy-heuristic;
PANNs (CNN14) verified working on this machine (checkpoint at
`~/panns_data/`, HF mirror `thelou1s/panns-inference` — zenodo is slow and
panns_inference's wget auto-download fails on Windows). Measured on the
test set (`ml/testclips/`): YAMNet — real scream 1.00, speech 0.00, white
noise 0.005, door-slam bursts 0.00; PANNs — real scream 0.69, all
non-distress ≤ 0.005. Key finding: YAMNet correctly rejects the synthetic
tone-stack scream as a *siren*, so the /node SIMULATE DISTRESS button and
`test_phone_mode.py` now send a committed REAL scream recording
(`hub/models/demo_scream.wav`, served at `/demo-scream`). Full suite:
78 passed. Keyword path ("help"/"bachao" via browser speech recognition)
unchanged. NOTE: `import dronekit` alone still fails on Py3.13
(`collections.MutableMapping`) — always go through `mavlink_interface.py`'s
shim; SITL e2e not yet re-run on this machine.

**Session 5b (2026-08-19) — Stage-1 trained on the RTX 3050 (real data).**
TF has no native-Windows GPU support, so `ml/train_torch_gpu.py` trains the
identical CNN in PyTorch/CUDA and ports weights into the Keras model for the
int8 TFLite export (parity gate: argmax agreement must be 1.0; ~2–3e-3 prob
drift from cuDNN/oneDNN float paths is normal). Data: ESC-50 (real
background + cry) + Kaggle `whats2000/human-screaming-detection-dataset`
(862 real screams + 2 631 real hard negatives; fetched anonymously via
`kagglehub`, cached in `~/.cache/kagglehub`) + `ml/data` bootstrap (help =
SAPI TTS). 5 973 files → 12 483 train samples; feature cache at
`ml/_cache/feats_seed0.npz` (`--cache-features`); best of 5 seeds by
val_loss. Test (real audio, file-level split): accuracy 0.87, background
FA rate 7.4%, scream P/R 0.66/0.56. Committed: `ml/out/stage1_int8.tflite`
(34 KB), `stage1_model_data.cc`, `stage1_metrics.json`; eval tool
`ml/eval_stage1_tflite.py`. KNOWN LIMIT: the help class is TTS-trained —
SAPI-style synthetic speech scores help≈1.0; record real keyword clips in
Phase 1 (live webapp keyword path uses speech recognition, unaffected).

## Current state & what's next

**Done:** v1 flight stack fully validated (unit + e2e SITL) with docs/IP
package; v2 Phase 0 (full chain in SITL, zero hardware —
`scripts/demo_phase0.py`) implemented.

**Next (v2 phases, per `docs/PROJECT_PLAN.md` §5):**
1. Phase 1 — audio bench: ESP32-S3 + INMP441 capture, TFLM Stage-1 model
   flashed, PANNs on the Pi 5; measure detection distance, latencies,
   false-positive rate.
2. Phase 2 — LoRa alert path: gateway ESP32 on the Pi's USB, AES-128
   sealed alerts, range/packet-loss measurements.
3. Phase 3 — drone build + manual→guided flights (F450 + Pixhawk 2.4.8,
   RC override mandatory, VLOS only).
4. Phase 4 — payload + camera + integrated field demo (scream → node →
   hub → drone → kit drop, one take, filmed).

**Still-valid v1 roadmap items** (fold in opportunistically): GitHub
Actions CI; dronekit → pymavlink migration + ArduPilot 4.x SITL;
fault-injection e2e scenarios; patent filing (user action — urgent, the
public repo is self-disclosure).

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
