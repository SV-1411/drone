# Implementation Plan — superseded by PROJECT_PLAN.md

**This document is the v1 roadmap and is superseded (2026-07-06) by
[`PROJECT_PLAN.md`](PROJECT_PLAN.md)**, the master plan for the project's
v2 concept — **VanniKawachh**, a distributed acoustic intelligence and
autonomous drone response network for women safety. The flight stack this
plan produced is now VanniKawachh's response layer, unchanged at its core.

## v1 history — what the original plan delivered

- **Phase 0 (software foundation) ✅** — full dispatch stack (trigger API,
  priority queue, 12-state mission executor, failsafe arbiter, dashboard),
  validated end-to-end in ArduPilot SITL: 37/37 unit tests, 6/6 SITL
  acceptance flights. Safety hardening shipped: verified mode setter,
  landing interlock, debounced arbitration, cancel/recall, auth,
  persistence.
- **Phase 1 (documentation & IP package) ✅** — research paper v2 (+.docx),
  print-ready thesis (+.docx), build & operations guide with budget BOM,
  8 original figures, two IPO Form-2 patent drafts with prior-art
  disclosure.
- v1 Phases 2–6 (software modernization, IP filing, hardware build, flight
  validation, productization) are absorbed into the v2 phases below; the
  still-standing items — CI, dronekit→pymavlink migration, fault-injection
  scenarios, patent filing — are tracked in `CLAUDE.md` § Current state.

## v2 phases (brief — full detail in `PROJECT_PLAN.md` §5)

| Phase | Scope | Status |
|---|---|---|
| **0 — SITL full chain** | Simulated node alert → hub pipeline → registry lookup → `POST /trigger` → SITL flight with hover-record + DELIVERING. Zero hardware (`scripts/demo_phase0.py`). | ✅ implemented |
| **1 — Audio bench** (2–3 weeks) | ESP32-S3 + INMP441 I2S capture; TFLM Stage-1 model flashed; clips over WiFi to the Pi 5; PANNs verification. Measure detection distance, Stage-1/-2 latency, false-positive rate. | pending |
| **2 — LoRa alert path** (1–2 weeks) | Gateway ESP32 on the Pi's USB; AES-128 sealed alerts over SX1278; registry lookup + pipeline on the hub. Measure range and packet loss. | pending |
| **3 — Drone build + flights** (3–4 weeks) | F450 + Pixhawk 2.4.8 build; bench → props-off → manual hover → GUIDED with RC override → full auto mission, open private field, VLOS only. | pending |
| **4 — Payload + integration** (2 weeks) | SG90 release servo, Pi Camera Module 3 hover recording, drop from ≤3 m; integrated field demo: scream → node → hub → drone → kit drop, one take, filmed. | pending |

Explicitly future work (papers, not prototype): live video streaming to
police, OpenCV victim tracking, multi-node TDOA localization, BVLOS
pilot-program operation, city-scale node mesh.

## Standing rules (unchanged from v1)

- Every phase ends with both test tiers green; hardware phases also end
  with the stage's acceptance properties observed on real telemetry.
- Safety regressions get a unit test before the fix is considered done.
- Spend order: time → filing fees → hardware. The simulator is free and
  most lessons are cheapest there.
