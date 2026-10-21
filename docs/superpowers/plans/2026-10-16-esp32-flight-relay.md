# ESP32 flight relay implementation plan

> **For agentic workers:** Execute inline using the approved design and checkpoints below.

**Goal:** Replace the Pi command receiver with tested, provisionable ESP32-S3
firmware that executes approved missions through TELEM2.

**Architecture:** A transport-independent C++ policy/state machine owns all
flight transitions. Arduino firmware supplies USB provisioning, NVS, TLS cloud
polling and MAVLink input/output. An independent task owns networking so HTTP
cannot stop MAVLink supervision.

**Tech Stack:** PlatformIO, Arduino ESP32, MAVLink common C headers, ArduinoJson,
NVS Preferences, Python provisioning/tests and an isolated local toolchain.

**Spec:** `docs/superpowers/specs/2026-10-16-esp32-flight-relay-design.md`

## Global constraints

- 1.0 m commanded relative-home altitude; 0.5 m/s horizontal target.
- Initial 20 m radius and 120 s total mission duration.
- Bench firmware is locked; validated commissioning enables ongoing approved
  missions across restarts. Interrupted flights always require local recovery.
- Optional local one-shot authorization expires after 120 s.
- Operator-approved verified voice commands only; authenticated TLS and 60 s expiry.
- Preserve the existing dirty worktree and original aircraft logs.
- No physical arm, takeoff, mission or motor commands during verification.
- Do not print credentials, commit secrets, disable pre-arm checks or claim flight validation.

## Task 1: Fresh relay command contract

**Files:** `hub/edge_relay.py`, `tests/test_edge_relay.py`

**Interface:** Existing claim response retains id/node_id/seq/lat/lon and adds
`created: float`, `expires_at: float`. Expired pending commands cannot be claimed.

- [ ] Add regression test with a fixed clock: queue a verified voice incident,
  approve it, claim once, require `expires_at == created + 60`, advance time and
  require a second expired command to return None.
- [ ] Add fields in the existing SQLite SELECT and returned dictionary.
- [ ] Run `python -m pytest tests/test_edge_relay.py -q` with repository dependencies.

## Task 2: Flight policy and controller

**Files:** `firmware/flight_relay/include/flight_policy.h`,
`firmware/flight_relay/test/test_policy.cpp`

**Interface:** `Telemetry`, `Command`, `Action`, `Controller::tick()`,
`Controller::accept()` and `Controller::confirm()` use no Arduino dependencies.

- [ ] Add C++ behavior tests for locked boot, valid mission progression,
  stale/invalid/duplicate commands, preflight rejection, mode/arm rejection,
  battery/GPS loss, pilot takeover, timeout, and land/disarm completion.
- [ ] Implement deterministic preflight and acknowledged state transitions.
  Every action returns an explicit type (mode, speed, arm, takeoff, waypoint,
  land); policy never directly writes a UART.
- [ ] Compile/run the tests with an available host C++ compiler, or execute
  the same controller against a software harness using a locally installed compiler.

## Task 3: Firmware transport and provisioning

**Files:** `firmware/flight_relay/platformio.ini`, `src/main.cpp`,
`scripts/provision_esp32_relay.py`, `firmware/flight_relay/README.md`

- [ ] Pin ESP32-S3 build dependencies. Configure USB CDC and GPIO44 RX/GPIO43 TX.
- [ ] Decode Pixhawk telemetry, request required messages/parameters and translate
  policy actions to MAVLink; require matching autopilot IDs and command ACKs.
- [ ] Use the same dashboard operator key for authenticated ESP claims/results,
  with a read-only device-status check. Retain optional legacy Pi compatibility.
- [ ] Add TLS cloud task, queue size bounds, clock/expiry checks and bounded
  result retries; do not consume new work during a mission or pending result.
- [ ] Add USB JSON provisioning into isolated NVS, redacted STATUS and local
  one-shot ENABLE/LOCK commands. Do not echo the raw provisioning request.
- [ ] Provisioning helper reads current Windows Wi-Fi credentials internally,
  prompts privately for the dashboard operator key, and verifies a redacted device reply.
- [ ] Compile `pio run -d firmware/flight_relay`. Fix all build errors.

## Task 4: Backup, bench flash and evidence

- [ ] Verify full 8 MB flash backup and SHA256 in ignored `.cache/`.
- [ ] Flash compiled firmware with flight locked; inspect redacted USB status.
- [ ] Verify TELEM2 heartbeat, GPS, RC and battery using read-only requests.
- [ ] Provision current Wi-Fi and operator key when locally available; use
  authenticated non-claiming endpoint to test credentials without launching.
- [ ] Document remaining blockers and retain flight lock until readiness passes.

No repository push or cloud deployment is a substitute for tests. Any cloud
schema extension needed by the new firmware must be deployed and checked before
the firmware can claim real commands successfully.
