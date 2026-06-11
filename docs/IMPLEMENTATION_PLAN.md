# Implementation Plan — From Validated Simulation to Operational System

A phased roadmap with entry/exit criteria and budget gates. Phases 0–1
are **done**; this document is the execution plan for everything after.

## Phase 0 — Software foundation ✅ (complete)

Full dispatch stack (trigger API, queue, executor, failsafe arbiter,
dashboard), validated: 37/37 unit tests, 6/6 SITL acceptance flights.
Safety hardening shipped: verified mode setter, landing interlock,
debounced arbitration, cancel/recall, auth, persistence.

## Phase 1 — Documentation & IP package ✅ (complete)

Research paper v2 (+.docx), print-ready thesis (+.docx), build &
operations guide with budget BOM, 8 original figures, two IPO Form-2
patent drafts with prior-art disclosure, this plan.

## Phase 2 — Software modernization (no money; ~2–4 sessions)

| Step | Exit criterion |
|---|---|
| 2.1 GitHub Actions CI running `pytest` on push | Green badge on README |
| 2.2 Replace DroneKit with pymavlink behind `mavlink_interface.py` | Unit suite + SITL test pass unchanged |
| 2.3 ArduPilot 4.x SITL in Docker/WSL2 as the test substrate | e2e PASS on Copter 4.x |
| 2.4 Fault-injection e2e scenarios (battery collapse, GPS denial, fence breach mid-flight) | Each scenario asserts the §5.5 response + touchdown |
| 2.5 TLS + per-operator tokens behind a reverse proxy recipe | Documented nginx config; WS auth |

## Phase 3 — IP filing (₹ fees + agent; calendar-bound, do early)

1. Official novelty search (InPASS, PATENTSCOPE) against both drafts'
   claims.
2. Engage a registered patent agent; decide merge vs two filings;
   redraw figures per Rule 15.
3. **File promptly** — the public repository is accumulating
   self-disclosure; in India the grace window is narrow.
4. Startup/individual fee reductions + expedited examination (Form 18A)
   where eligible.

## Phase 4 — Hardware build (~₹36,000 minimum / ~₹58,000 recommended)

Procurement, assembly, calibration, and bring-up per
`BUILD_AND_OPERATIONS_GUIDE.md` + `HARDWARE_INTEGRATION.md`.
Gate to Phase 5: props-off arming test passes; HUD telemetry clean;
`/health` shows `vehicle_connected` over TELEM2.

## Phase 5 — Flight validation (regulatory prerequisites first)

UIN registration on DigitalSky; permitted-zone confirmation; pilot +
RC kill path mandatory at every stage.

| Stage | Gate to next |
|---|---|
| Manual hover | Stable, vibrations within ArduPilot norms |
| Single GUIDED leg (30 m) | Mode confirm + leg telemetry nominal |
| Short full autonomous cycle (≤100 m) | 8/8 acceptance properties on real telemetry |
| Envelope expansion | Repeatable missions; archive shows consistent battery curves |

## Phase 6 — Productization (optional, demand-driven)

Multi-vehicle routing layer; 4G/LTE link + cloud relay; camera/WebRTC
feed; operator identity/RBAC; signed mission records; pilot console
hardening. Each item has a stub design in `SYSTEM_DOCUMENTATION.md` §12.

## Standing rules

- Every phase ends with both test tiers green; hardware phases also end
  with the stage's acceptance properties observed on real telemetry.
- Safety regressions (anything touching §4–§5 of the paper/thesis) get a
  unit test before the fix is considered done.
- Spend order: time → filing fees → hardware. The simulator is free and
  most lessons are cheapest there.
