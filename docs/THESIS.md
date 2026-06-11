# Design, Implementation, and Safety Validation of a Trigger-Driven Autonomous UAV Dispatch System with Verified Command Delivery

**A Thesis**

**Submitted in partial fulfilment of the requirements for the degree of**
*(degree, to be filled in)*

**by**
*(candidate name)*

**under the supervision of**
*(supervisor name)*

*(institution)* · *(department)*
**June 2026**

---

## Declaration

I declare that this thesis is my own work, carried out by me, and that all
sources of material used — software libraries, protocol specifications,
regulatory texts, and patent documents — are cited in the References. The
software described herein is published under the repository
<https://github.com/SV-1411/drone.git>, and all experimental results
reported are reproducible from that repository as described in Chapter 6.
A large-language-model assistant was used during drafting for structure
and consistency; all technical content derives from the implementation
and its test logs, and every sentence was reviewed and accepted by the
author.

*(Signature, date — to be completed.)*

---

## Abstract

Small multirotor aircraft running open-source autopilot firmware can
navigate, hold position, and recover from faults without a pilot, yet the
software layer that turns an external event into a complete, safe,
unattended flight remains the weak link of autonomous operations. This
thesis designs, implements, and validates such a layer: a trigger-driven
dispatch system in which an HTTP request carrying a target coordinate is
transformed — with zero human piloting — into an armed takeoff, transit,
dwell, return, and landing, supervised throughout by a failsafe arbiter
and observable through a live map dashboard.

The thesis makes four contributions. First, a **verified mode-transition
protocol** that treats the autopilot as an unreliable command sink: every
flight-mode command, nominal or emergency, is re-issued through layered
MAVLink encodings until the autopilot's own telemetry confirms adoption,
with a cross-action fallback (return-to-launch ⇄ land) when confirmation
fails. The need is demonstrated empirically: the standard client idiom
for entering GUIDED mode is silently ignored by the ArduCopter 3.3
simulator while reporting success. Second, a **landing-interlocked
dispatch pipeline**: five gates from network edge to touchdown guarantee,
structurally, that a serial mission queue can never start a flight
against an airborne vehicle. Third, a **debounced, severity-ordered
failsafe arbiter** in which a land demand is never downgraded, transient
sensor dropouts cannot trigger a landing, and escalation is honoured even
mid-return. Fourth, a **two-tier validation methodology** — a 37-case
unit suite over the safety logic plus end-to-end software-in-the-loop
acceptance flights — under which the system achieved 0.4–0.6 m terminal
accuracy against a 5 m tolerance across six 896 m missions, returning to
within 0.2 m of home.

The thesis further specifies the complete transition to hardware: a
minimum-budget (~₹36,000) Pixhawk-based airframe, its wiring and
calibration, the regulatory envelope under India's Drone Rules 2021, and
a staged flight-test progression. An intellectual-property analysis
distinguishes the contributions from the dense patent landscape of
trigger-dispatched UAVs and presents two draft patent specifications.

---

## Table of Contents

1. Introduction
2. Background and Literature Review
3. System Design
4. Implementation
5. Safety Engineering
6. Evaluation
7. Hardware Realization and Regulatory Context
8. Intellectual Property Analysis
9. Conclusions and Future Work
References
Appendix A — API Reference Summary
Appendix B — Configuration Reference
Appendix C — Test Inventory

---

# Chapter 1 — Introduction

## 1.1 Motivation

Consider three operational scenarios. A perimeter sensor on an industrial
site detects an intrusion at 02:40 and the site has no pilot on shift. A
public-health network needs a blood sample moved 4 km across a congested
city within fifteen minutes. A disaster-response cell receives a
coordinate from a field team and needs eyes on it now. In each case the
*aircraft* able to perform the flight exists as commodity hardware; what
is missing is trustworthy software that converts the **event** into a
**flight** with nobody touching a controller.

The off-the-shelf answer — a human operator running Mission Planner or
QGroundControl — reintroduces precisely the dependency the scenarios
exclude: a trained pilot, present, awake, and attentive. The research
answer — full robotics middleware such as ROS 2 with MAVROS — carries a
dependency and complexity footprint disproportionate to the task and
awkward on the Raspberry-Pi-class computers that ride on small airframes.
The gap is a *dispatch layer*: small enough to live on the aircraft,
complete enough to be trusted with it.

## 1.2 The deceptive difficulty of the dispatch layer

A dispatch layer looks trivial — "send the drone to a coordinate" is a
few dozen lines against any MAVLink client library. The difficulty is
concentrated in the failure cases, three of which this thesis treats as
central:

**Silent command rejection.** During this work, the standard
DroneKit-Python idiom for entering GUIDED mode (`vehicle.mode =
VehicleMode("GUIDED")`) was observed to fail silently against the
ArduCopter 3.3 SITL build: the library reflects the assignment, no error
is raised, the autopilot stays in STABILIZE, and the subsequent takeoff
command is ignored. The aircraft does nothing, and the software believes
everything is fine. With a human in the loop this is an annoyance; in an
unattended system it is a stranded mission — and if the same unverified
pathway carries the *emergency* commands, it is a stranded mission that
cannot even be recalled.

**Mission overlap.** A queue that starts mission *N+1* when mission *N*
"finishes" relies on a definition of *finished*. If an abort path merely
commands return-to-launch and returns control, the queue's next mission
begins its arming sequence against an aircraft still in the air. The
resulting behaviour — re-entering GUIDED mid-descent, issuing a takeoff
command to an airborne vehicle — is undefined in the worst sense.

**Failsafe interaction.** Hazard monitors are individually simple and
collectively subtle. A critical-battery land must beat an in-progress
low-battery return — even after the return began. A one-second GPS
dropout must *not* land the aircraft in a river. A condition that
persists (low battery persists by definition) must not re-fire at the
polling rate and bury the incident record.

## 1.3 Problem statement

*Design and implement a companion-computer software system that converts
an authenticated network trigger into a complete autonomous mission on an
unmodified ArduPilot autopilot, such that: (i) every flight-mode command
is positively confirmed from autopilot telemetry, with bounded retry and
defined fallback; (ii) no mission can begin while the vehicle is airborne
or armed; (iii) hazard responses obey debounce, severity, and escalation
semantics; and (iv) these properties are demonstrated by automated,
reproducible tests rather than asserted.*

## 1.4 Scope

In scope: the dispatch layer (trigger surface, queue, mission executor,
failsafe arbiter, persistence, dashboard), its validation in SITL, and
the complete specification of a hardware build. Out of scope: guidance,
navigation, and control theory (the autopilot's stack is used as
supplied); GPS-denied flight; multi-vehicle fleets (designed-for,
discussed in Chapter 9, not implemented); and beyond-visual-line-of-sight
operations approval.

## 1.5 Contributions

1. The verified mode-transition protocol (§4.4, §5.3).
2. The landing-interlocked dispatch pipeline and its invariant (§5.4).
3. The debounced, severity-ordered failsafe arbiter (§5.5).
4. The two-tier validation methodology and its results (Chapter 6).
5. A complete, costed hardware realization path with regulatory mapping
   (Chapter 7) and an IP analysis with two draft specifications
   (Chapter 8).
6. The open-source implementation itself, ~2,500 lines of Python and
   JavaScript with documentation, published for reproduction.

## 1.6 Thesis organization

Chapter 2 reviews the technology base and related work. Chapter 3
presents requirements and architecture. Chapter 4 details implementation.
Chapter 5 develops the safety engineering, the thesis's core. Chapter 6
defines methodology and reports results. Chapter 7 specifies hardware
realization. Chapter 8 analyses intellectual property. Chapter 9
concludes.

---

# Chapter 2 — Background and Literature Review

## 2.1 The open-source autopilot stack

**ArduPilot** [1] is a two-decade-old open-source autopilot supporting
multirotor (Copter), fixed-wing, ground, and marine vehicles. Its Copter
firmware provides the flight modes this work depends on: STABILIZE
(manual), GUIDED (companion-commanded positions), RTL (autonomous return
and land), and LAND (descend in place). Internally it runs an Extended
Kalman Filter fusing IMU, magnetometer, barometer, and GNSS, and enforces
its own pre-arm checks and failsafes. **PX4** is the principal
alternative; this work targets ArduPilot but communicates only through
the protocol layer, leaving a PX4 port a matter of mode-name mapping.

**MAVLink** [2] is the de-facto micro-air-vehicle protocol: compact
binary messages over serial, UDP, or TCP. Five messages matter here:
HEARTBEAT (1 Hz liveness + current mode), GLOBAL_POSITION_INT and
GPS_RAW_INT (position and fix quality), SYS_STATUS/BATTERY_STATUS
(power), COMMAND_LONG (parameterized commands, including
MAV_CMD_DO_SET_MODE), and SET_MODE (the older mode-change message). The
existence of *two* mode-change encodings plus per-library setters is
exactly the redundancy the verified setter of §5.3 exploits.

**DroneKit-Python** [3] wraps pymavlink [4] in a vehicle-object API. Its
final release (2.9.2, 2019) predates Python 3.10; §4.2 describes the
compatibility shim that keeps it serviceable. The library's
convenience — attribute-style telemetry, `simple_takeoff`,
`simple_goto` — made it the right scaffolding for this work, but its
unverified setters are a documented hazard this thesis corrects for;
Chapter 9 outlines the planned migration to pymavlink/MAVSDK.

**SITL** — software-in-the-loop — runs the autopilot firmware as a host
process against simulated dynamics, exposing a MAVLink stream
indistinguishable from hardware [1][5]. The `dronekit-sitl` package
ships prebuilt binaries; its only Windows Copter build is 3.3 (2015).
This vintage proved a feature for safety research: older firmware
exhibits the command-delivery faults that newer firmware shows only
intermittently, forcing the defensive design that newer firmware still
benefits from.

## 2.2 Ground-control software

Mission Planner and QGroundControl are mature, pilot-centric GCS
applications. Both can upload missions and issue GUIDED commands, and
both can be scripted after a fashion, but neither offers a first-class
machine-facing dispatch API, separation between dispatch and viewing, or
a queue with safety semantics. They are also desktop applications — the
wrong shape for an embedded companion stack. This work treats GCS
software as a *setup* tool (firmware flashing, calibration, parameters)
and replaces its operational role.

## 2.3 Companion-computer architectures

The companion-computer pattern — a Linux board on the airframe speaking
MAVLink to the flight controller — is well established in the ArduPilot
ecosystem [1]. Published stacks range from bare pymavlink scripts to
ROS 2 + MAVROS. The middle of that range is thin: stacks that are
production-shaped (authentication, persistence, observability, tests)
without robotics-middleware weight. This work sits deliberately in that
middle.

## 2.4 The patent landscape

Because Chapter 8 develops patentability, the literature review includes
patents. Trigger-to-coordinate dispatch is densely claimed:
US 10,216,181 B2 (sensor-triggered rescue UAV to a recorded GPS
location); US 10,089,889 B2 (emergency-call-initiated dispatch,
self-guided flight, 911 integration); US 12,184,803 B2 (emergency
dispatch with diagnostics); US 9,573,684 B2 and US 10,737,782 B2
(delivery dispatch-and-return). Firmware failsafes are non-patent prior
art via ArduPilot/PX4 documentation. None of these documents, to the
author's knowledge, discloses telemetry-confirmed mode transition with
layered re-encoding, a landing interlock as a queue invariant, or
companion-level arbitration semantics — the distinction Chapter 8
develops into claims.

## 2.5 Regulatory context

India's **Drone Rules, 2021** [15] classify UAVs by mass (the builds of
Chapter 7 fall in *Micro*, 250 g–2 kg, or *Small*, 2–25 kg), mandate
registration (UIN) via the DigitalSky platform, and constrain operations
by airspace zone. The U.S. equivalent, FAA Part 107 [13], shapes the
120 m altitude ceiling adopted as a validation bound in this work.
Common to all regimes: autonomy does not remove the requirement for a
responsible operator able to take control — which the architecture
honours by leaving the hardware RC link entirely outside the software's
authority.

---

# Chapter 3 — System Design

## 3.1 Requirements

**Functional.** F1: accept an authenticated HTTP trigger carrying target
coordinate, priority, optional altitude and dwell. F2: execute the
mission fully autonomously: arm, take off, transit, dwell, return, land.
F3: stream telemetry at 2 Hz to a viewer. F4: accept mid-flight waypoint
detours. F5: accept recall (cancel) of queued and running missions.
F6: persist the mission record across restarts.

**Safety.** S1: every mode command confirmed from telemetry (no trust in
client state). S2: no mission may start against an armed/airborne
vehicle. S3: hazard responses debounced, severity-ordered, escalating,
fire-once. S4: requests outside the geofence rejected before flight.
S5: altitude bounded 2–120 m at the validation edge. S6: on process
shutdown with an armed vehicle, command return before disconnecting.
S7: no manual piloting surface anywhere in the system.

**Non-functional.** N1: deployable on a Raspberry-Pi-class computer in
one Python virtual environment. N2: identical code in SITL, Docker, and
hardware, differing only in environment variables. N3: the safety logic
testable in milliseconds without a simulator. N4: viewer operable on
networks without internet access.

## 3.2 Architecture

Four components, two protocols (Figure 1: `figures/architecture.png`):

- **flight_core** — the mission executor (a twelve-state machine),
  MAVLink interface, failsafe arbiter, and configuration. Speaks only
  MAVLink; serves nothing.
- **trigger_api** — FastAPI application owning the executor: trigger,
  status, cancel, waypoint, telemetry REST + WebSocket, health,
  archive. Speaks only HTTP/WS upward and in-process calls downward.
- **dashboard** — React + Leaflet viewer; consumes JSON; no MAVLink, no
  flight controls.
- **autopilot substrate** — ArduPilot SITL or a Pixhawk-class flight
  controller; the swap is one connection string (N2).

The decision with the longest consequences is that **the dashboard and
the flight core never meet**: every interaction crosses the trigger API,
which is therefore the single place where authentication, validation,
and rate limits live, and the only component that holds both ends.

## 3.3 Mission lifecycle

The executor's state machine (Figure 2: `figures/state_machine.png`)
threads IDLE → CONNECTING → WAITING_GPS → ARMING → TAKEOFF → ENROUTE →
HOVERING → RTL → LANDED → COMPLETED, with ABORTED and FAILED as
abnormal terminals. Three properties hold for every state: no state
waits for human input; every transition is timestamped into the mission
log; and every blocking loop polls both the failsafe arbiter and the
operator-cancel flag, so abnormal termination is reachable from
anywhere (the dashed edges of Figure 2).

## 3.4 Queue semantics

One aircraft implies serial execution. The queue is bounded (admission
refused with HTTP 429 beyond a configured depth), priority-ordered
(critical ≻ high ≻ normal ≻ low, FIFO within a class), and
persistence-backed (SQLite; records orphaned by a crash are surfaced as
`interrupted` on restart). Its safety obligations — the landing
interlock — are specified in §5.4.

---

# Chapter 4 — Implementation

## 4.1 Codebase shape

~1,900 lines of Python across `flight_core/` (executor 600, arbiter 150,
MAVLink interface 85, configuration 130) and `trigger_api/` (application
230, queue 200, persistence 120, models 80), ~600 lines of
JavaScript/JSX in `dashboard/`, and ~700 lines of tests. No framework
beyond FastAPI; concurrency is standard-library threading on the flight
side and asyncio only at the HTTP/WebSocket surface.

## 4.2 Keeping DroneKit alive on modern Python

DroneKit 2.9.2 imports `collections.MutableMapping`, removed in Python
3.10 [14]. Before importing it, the MAVLink interface re-aliases the
abstract base classes onto `collections`, and the `future` package
supplies `past.builtins.basestring`. The shim is seven lines, confined
to one module, and documented as temporary scaffolding pending the
pymavlink migration (Chapter 9).

## 4.3 Concurrency model

Three thread families coexist: DroneKit's reader thread (updates vehicle
attributes), the queue worker (runs at most one mission), the failsafe
arbiter (1 Hz), and a telemetry recorder (breadcrumb path). Shared state
is confined behind one re-entrant lock in the executor and one lock in
the arbiter; the API reads an atomic *snapshot* assembled under the
lock rather than touching live vehicle objects. Two races found by
review are closed structurally: concurrent connection attempts (eager
connect vs first mission) serialize behind a connect lock, and the
blocking connect call is moved off the asyncio event loop with
`asyncio.to_thread` so the HTTP surface stays responsive during
connection storms.

## 4.4 The verified setter in code

The protocol of §5.3 is one routine, `_set_mode_confirmed`, plus a raw
escape hatch `_raw_set_mode` that resolves the autopilot's mode mapping
and emits COMMAND_LONG(MAV_CMD_DO_SET_MODE) and SET_MODE back-to-back.
Every mode change in the codebase — arming-phase GUIDED, RTL, LAND,
abort actions, shutdown RTL — routes through it; the bare setter appears
nowhere outside the routine. This "single chokepoint" structure is
itself a safety property: a reviewer can verify S1 by grepping for mode
assignments.

## 4.5 The dispatch surface

FastAPI models validate at the edge: coordinate ranges, altitude
2–120 m, hover 0–3600 s, priority vocabulary, and — beyond Pydantic —
geofence containment of targets and waypoints computed by haversine
distance from home. Authentication is a shared token in the `X-API-Key`
header, enabled by setting `API_TOKEN` (deliberately optional so SITL
development is frictionless, deliberately loud in documentation that
production must set it). The WebSocket stream sends the full snapshot
at 2 Hz but the breadcrumb path only every fourth frame; the dashboard
merges, halving steady-state bandwidth without visible effect.

## 4.6 Persistence

A single-table SQLite store (`missions`) written on enqueue, start, and
finish. The store is best-effort by design: a persistence failure logs
and never blocks dispatch (availability of the safety function outranks
durability of the record). On startup, rows still marked
queued/running are flipped to `interrupted` — an honest record of a
crash, surfaced via `GET /missions/archive`.

## 4.7 The viewer

React 18 + Leaflet over OpenStreetMap: home/target markers, a
heading-rotated drone marker, breadcrumb polyline, telemetry panel,
dispatch and detour forms, recall button, incident log. Two operational
details matter more than they look: map assets are bundled at build
time (field networks rarely have internet), and auto-follow of the
drone is a toggle (an operator inspecting the route must not fight the
camera).

---

# Chapter 5 — Safety Engineering

## 5.1 Hazard analysis

A compact HAZOP-style pass over the mission lifecycle yields the hazard
set the design must close:

| ID | Hazard | Worst credible outcome | Closed by |
|---|---|---|---|
| H1 | Mode command silently rejected | Stranded/uncontrolled aircraft; unrecallable mission | §5.3 verified setter |
| H2 | Emergency command (RTL/LAND) not delivered | Failsafe ineffective at the moment it matters | §5.3 + cross-action fallback |
| H3 | New mission starts while airborne | Takeoff commanded to flying vehicle; undefined behaviour | §5.4 interlock |
| H4 | Transient GPS dropout treated as loss | Unnecessary landing on unsafe ground | §5.5 debounce |
| H5 | Critical battery during RTL | Aircraft presses home and falls short | §5.5 mid-return escalation |
| H6 | Demand downgraded (LAND→RTL) | Wrong recovery flown | §5.5 monotone severity |
| H7 | Target beyond geofence accepted | Predictable mid-air abort; wasted battery at distance | edge validation |
| H8 | Wind stall / rejected goto | Battery exhausted loitering | leg-stall detector |
| H9 | Process shutdown mid-flight | Aircraft abandoned under autopilot defaults | shutdown RTL |
| H10 | Dispatch by unauthorized party | Aircraft weaponized by anyone on the network | token auth + (deployment) TLS |

## 5.2 Defence-in-depth structure

The closures arrange into five serial gates (Figure 7:
`figures/safety_interlock.png`): edge validation → queue admission →
pre-flight interlock → in-flight guards → abort guarantee. The
architecture's invariant — *the queue can never start a flight against
an airborne vehicle* — emerges from gates 3 and 5 jointly, and is the
single sentence a reviewer should test the system against.

## 5.3 Verified mode transition

Stated as a protocol: issue through the high-level interface; loop until
deadline reading the autopilot's HEARTBEAT-derived mode; every 700 ms of
non-confirmation re-issue through COMMAND_LONG(MAV_CMD_DO_SET_MODE) and
SET_MODE and re-poke the high-level setter; success iff the *autopilot
reports* the requested mode. Failure on the abort path triggers the
cross-action fallback: an unconfirmable RTL becomes a LAND attempt and
vice versa — some confirmed recovery beats an optimal unconfirmed one.
Idempotence of mode-setting makes the retry loop safe; reading
confirmation from the autopilot's own report makes it sound. Empirical
behaviour: on ArduCopter 3.3 SITL, convergence within two retries; the
original silent-rejection failure becomes a logged, retried, recovered
event.

## 5.4 The landing interlock

Two mechanisms, redundant by intent. The **abort guarantee**: every
abnormal termination (failsafe, recall, exception-with-airborne-vehicle)
commands its action through §5.3 and then blocks — polling armed state
and relative altitude — until disarm or a 240 s bound, before the queue
regains control. The **pre-flight check**: a dequeued mission re-reads
the armed flag and waits (bounded) or fails rather than arm an armed
vehicle. Either mechanism alone closes H3 in the common case; together
they make the invariant structural rather than probabilistic. The same
property is defended at process boundaries: shutdown with an armed
vehicle commands RTL (verified) before the MAVLink link drops (H9).

## 5.5 Failsafe arbitration

The arbiter evaluates four condition families at 1 Hz — battery low
(20%) and critical (10%), GPS fix validity, geofence distance, mission
wall-clock — and maintains exactly one demanded action under three
rules. **Monotone severity**: demands only escalate (NONE < RTL < LAND);
H6 closed by construction. **Debounce**: GPS loss fires only after N
(default 3) consecutive bad samples, reset on recovery; it demands LAND
because a return path is non-navigable without positioning; H4 closed
with detection latency bounded at N seconds. **Fire-once**: each named
hazard emits once per mission, re-emission permitted only as
escalation — the incident record stays a record. The executor couples to
the arbiter inside every blocking loop, *including the RTL loop*, which
re-reads the demand each second and swaps to LAND on escalation (H5).

## 5.6 What the software refuses to own

Two authorities stay outside the stack by design. The hardware RC link
(pilot mode-switch and kill) overrides anything this software commands —
the architecture's last line is not software at all. And ArduPilot's own
pre-arm checks and firmware failsafes stay at stock values on hardware:
the SITL-only relaxation is dead code unless `SITL_MODE=1`, and the
documentation treats setting it on a real aircraft as a defect, not an
option.

---

# Chapter 6 — Evaluation

## 6.1 Methodology

Validation is two-tier by design (requirement N3): properties that can
be checked in milliseconds must not require a flight.

**Tier 1 — unit suite (37 cases, ~13 s, no simulator).** A synthetic
vehicle object drives the arbiter through every rule of §5.5: low →
RTL; critical → LAND, including over an in-progress RTL; never
downgrade; N−1 bad GPS samples → no trigger, N → trigger, recovery
resets; fire-once; geofence and timeout. Queue tests cover priority
order, depth rejection, cancel of queued and of running missions
(asserting `request_abort` reaches the executor), history pruning that
never drops active missions, and worker bookkeeping. Persistence tests
cover round-trip and crash-orphan marking. Validation tests cover every
rejection bound. Configuration tests pin env-at-construction semantics.
The suite *discriminates*: run against the pre-hardening implementation,
the debounce, cancel, and interlock cases fail — the tests encode the
safety claims, not the code's reflection.

**Tier 2 — SITL acceptance flight.** The harness boots `dronekit-sitl
copter-3.3` and the API as child processes, dispatches the 896 m New
Delhi test mission (alt 15 m, dwell 5 s), polls telemetry at 1 Hz, and
asserts eight properties: SITL listening, API listening, vehicle
connected, armed, took off (≥80% of target altitude), reached target
(closest approach ≤ 5 m), returned home (≤ 10 m, **required**), landed.
No tolerance widening is applied.

## 6.2 Results

Six end-to-end missions span the development arc (Windows 11, Python
3.11.9):

| Metric | Run 2 | Run 3 | Run 4 | Run 5 | Run 6 (hardened) |
|---|---|---|---|---|---|
| Wall-clock (s) | 503.7 | 321.6 | 321.3 | 330.7 | 331.3 |
| Closest approach (m) | 0.4 | 0.5 | 0.4 | 0.4 | 0.6 |
| Final distance from home (m) | 0.1 | 0.0 | 0.0 | 0.0 | 0.0–0.2 |
| Verdict | PASS† | PASS | PASS | PASS | PASS (8/8) |

† harness predicate bug, §6.3 case 2; verdict unaffected.

Unit tier: 37/37 on the hardened implementation. Terminal accuracy sits
an order of magnitude inside tolerance — bounded by the autopilot's
loiter behaviour, not the dispatch layer. Wall-clock variance across
runs 3–6 is <3%, dominated by simulator boot.

## 6.3 Defect case studies

Three defects found during the work are retained as evidence for the
design philosophy.

**Case 1 — the silent mode rejection (run 1).** Symptom: state machine
reached TAKEOFF, altitude stayed 0.0 m, vehicle disarmed itself. Log
forensics showed mode still STABILIZE despite the client reporting
GUIDED. Root cause: unverified setter (H1). Fix: §5.3. Lesson: *the
autopilot's report is the only truth; the client's state is a wish.*

**Case 2 — the racing test predicate (run 2).** The harness inferred
"connected" from a telemetry state string that the connect path had
begun parking at IDLE; the inference raced the transition. Fix: an
explicit boolean on `/health`. Lesson: tests must consume *interfaces*,
not coincidences of internal state.

**Case 3 — the unguarded abort path (found by review, closed before it
fired).** The original `_abort` used the bare setter — the exact call
proven unreliable in Case 1 — and returned with the vehicle airborne
(H2+H3 compound). The unit tier now contains the regression tests that
would have caught both. Lesson: *the emergency path must be held to a
higher standard than the nominal path, and it is the one most easily
left to a lower one.*

## 6.4 Threats to validity

Firmware vintage (Copter 3.3; 4.x validation pending — though §5.3 is a
superset of what 4.x needs); environmental idealism (no wind, perfect
GPS in SITL; sensor faults injected only synthetically in tier 1);
single-vehicle scope; security model bounded at shared-token + geofence
(no TLS/replay protection inside the stack). Each maps to a Chapter 9
work item.

---

# Chapter 7 — Hardware Realization and Regulatory Context

*(Full procurement and assembly detail lives in
`docs/BUILD_AND_OPERATIONS_GUIDE.md`; wiring, parameters, and
calibration in `docs/HARDWARE_INTEGRATION.md`. This chapter summarizes
the engineering decisions.)*

## 7.1 Airframe selection and budget

The minimum viable platform is an F450-class quadcopter: Pixhawk 2.4.8
flight controller, u-blox M8N GNSS+compass, 2212/920 kV motors with 30 A
ESCs and 1045 propellers, 3S 5200 mAh LiPo, FlySky six-channel RC link,
and a Raspberry Pi Zero 2 W companion — ≈ ₹36,000 at Indian retail
(Figure 6: `figures/hardware_architecture.png`; wiring in Figure 8:
`figures/wiring.png`). The recommended tier (~₹58,000) upgrades to a
current-generation autopilot (Pixhawk 6C), M10 GNSS, Pi 4, telemetry
radio, and a second battery. The cost driver is the autopilot; nothing
in the dispatch layer requires the expensive one — the budget build runs
identical software (requirement N2).

## 7.2 Integration

The companion computer connects to the autopilot's TELEM2 UART at
921600 baud; `MAVLINK_CONNECTION=/dev/serial0,921600` is the single
configuration change from SITL. Production deployment is a systemd unit
with `API_TOKEN` set and `SITL_MODE` unset, so ArduPilot pre-arm gating
remains stock (§5.6). The RC transmitter is bound, with the mode switch
and motor-kill assigned, *before* the first arming test.

## 7.3 Flight-test progression

Five stages, each gating the next: props-off arming on the bench;
manual hover (pilot on RC) for stability and vibration; one short
GUIDED leg (30 m, 10 m altitude) with the pilot's hand on the switch; a
tethered/short full autonomous cycle (trigger → hover → RTL within
100 m); then envelope expansion. The acceptance criteria at each stage
are the same eight properties the SITL harness asserts, observed on
real telemetry.

## 7.4 Regulatory mapping (India)

Under the Drone Rules 2021 [15]: register the aircraft for a UIN on
DigitalSky; operate in permitted zones only (check the airspace map
per flight); the builds of §7.1 fall in Micro (if <2 kg AUW) or Small
class; remote-pilot certification requirements apply per class and
operation; and the 120 m altitude bound enforced at the API edge mirrors
the regulatory ceiling. The system's no-manual-piloting design does not
remove the requirement for a responsible pilot in command with override
capability — the RC link of §7.2 is that capability.

---

# Chapter 8 — Intellectual Property Analysis

## 8.1 Landscape

Trigger-dispatched UAVs are densely patented (US 10,216,181 B2;
US 10,089,889 B2; US 12,184,803 B2; delivery families US 9,573,684 B2,
US 10,737,782 B2): a filing that claims "launch a drone to a coordinate
upon an external trigger" fails on its face. Firmware failsafes are
non-patent prior art (ArduPilot/PX4 documentation).

## 8.2 The distinguishable layer

What the landscape does not disclose, to the author's knowledge, is the
*assurance layer*: (i) telemetry-confirmed mode transition with layered
re-encoding and cross-action emergency fallback; (ii) the landing
interlock as a structural queue invariant; (iii) companion-level
arbitration semantics (monotone severity, debounce-with-reset,
mid-recovery escalation, fire-once). Two draft complete specifications
in Indian Patent Office Form-2 structure are included in the repository
(`docs/patents/`): Draft 1 claims (i)+(ii) as method and system; Draft
2 claims (iii) as method and system. Both disclose the known art
honestly and are drafted to be distinguishable from it.

## 8.3 Honest assessment and process

Patentability is decided by an examiner, not an author. The drafts
require: an official novelty search (IPO InPASS, WIPO PATENTSCOPE)
against the *claims*; engagement of a registered patent agent for claim
scoping, Rule-15 drawings, and filing (Forms 1/2/3/5, 18/18A); and an
urgent assessment of self-disclosure — this repository is public, and in
India the grace provisions are narrow, so the publication dates of the
repository weigh on novelty and argue for filing promptly rather than
polishing further.

---

# Chapter 9 — Conclusions and Future Work

## 9.1 Conclusions

A dispatch layer becomes trustworthy not by adding intelligence but by
removing trust: treat the autopilot as an unreliable command sink and
prove adoption from its telemetry; treat "mission finished" as a claim
requiring evidence (disarmed, on the ground) before the next mission may
exist; treat failsafe policy as an arbitration problem with stated
semantics rather than a pile of triggers. Under those three disciplines,
the failure modes observed and analysed in this work — silent mode
rejection, mission overlap, glitch-triggered landings, downgraded
emergencies — become either retried-and-recovered events or cleanly
failed missions. The implementation validates end-to-end in simulation
with terminal accuracy an order of magnitude inside tolerance, its
safety semantics pinned by a unit suite fast enough for CI, and its
hardware path specified to the last connector and rupee.

## 9.2 Future work

1. **Autopilot layer modernization** — replace DroneKit with
   pymavlink/MAVSDK; validate against ArduPilot 4.x SITL; port the
   verified setter to PX4 mode identifiers.
2. **Fault-injection flight campaign** — scripted SITL scenarios
   (battery collapse, GPS denial windows, fence breach) measuring
   response latency and touchdown dispersion; then
   hardware-in-the-loop.
3. **Security hardening** — TLS termination, per-operator identity,
   replay protection, signed mission records.
4. **Multi-vehicle dispatch** — per-vehicle executors under a routing
   layer (nearest-available, energy-aware); the interlock invariant
   becomes per-airframe.
5. **GPS-denied resilience** — optical flow / visual odometry as a
   landing-quality degraded mode, raising the GPS-loss response from
   "land now" to "land well."
6. **Field validation** — the Chapter 7 progression flown on the
   documented build, with the thesis's acceptance properties observed
   on real telemetry.

---

# References

1. ArduPilot Project — firmware, SITL, and failsafe documentation.
   <https://ardupilot.org>. Accessed 2026-06-11.
2. MAVLink Developer Guide — protocol specification (HEARTBEAT,
   SET_MODE, COMMAND_LONG/MAV_CMD_DO_SET_MODE).
   <https://mavlink.io/en/>. Accessed 2026-06-11.
3. DroneKit-Python 2.9.2.
   <https://github.com/dronekit/dronekit-python>. Accessed 2026-06-11.
4. pymavlink. <https://github.com/ArduPilot/pymavlink>. Accessed
   2026-06-11.
5. dronekit-sitl 3.3.0. <https://github.com/dronekit/dronekit-sitl>.
   Accessed 2026-06-11.
6. FastAPI. <https://fastapi.tiangolo.com>. Accessed 2026-06-11.
7. Uvicorn. <https://www.uvicorn.org>. Accessed 2026-06-11.
8. React 18. <https://react.dev>. Accessed 2026-06-11.
9. Vite 5. <https://vite.dev>. Accessed 2026-06-11.
10. Leaflet 1.9. <https://leafletjs.com>. Accessed 2026-06-11.
11. OpenStreetMap. <https://www.openstreetmap.org>. Accessed 2026-06-11.
12. Pixhawk hardware reference. <https://pixhawk.org>. Accessed
    2026-06-11.
13. U.S. FAA, Part 107 — Small Unmanned Aircraft Systems.
    <https://www.faa.gov/uas/commercial_operators>. Accessed 2026-06-11.
14. Python 3.10 — What's New (collections ABC relocation).
    <https://docs.python.org/3.10/whatsnew/3.10.html>. Accessed
    2026-06-11.
15. Ministry of Civil Aviation, Government of India — The Drone Rules,
    2021; DigitalSky platform. <https://digitalsky.dgca.gov.in>.
    Accessed 2026-06-11.
16. Patent documents: US 10,216,181 B2; US 10,089,889 B2;
    US 12,184,803 B2; US 9,573,684 B2; US 10,737,782 B2 (Google
    Patents / USPTO full-text).

---

# Appendix A — API Reference Summary

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/trigger` | X-API-Key* | Validate + enqueue mission; returns id, ETA |
| GET | `/mission/{id}` | — | Mission status |
| POST | `/mission/{id}/cancel` | X-API-Key* | Recall (dequeue / abort-to-RTL) |
| POST | `/mission/{id}/waypoint` | X-API-Key* | Mid-flight detour |
| GET | `/missions` | — | Recent history (memory) |
| GET | `/missions/archive` | — | Persisted history (SQLite) |
| GET | `/telemetry` | — | Snapshot |
| WS | `/ws/telemetry` | — | 2 Hz stream |
| GET | `/health` | — | Liveness, connectivity, queue depth |

\* enforced when `API_TOKEN` is set.

# Appendix B — Configuration Reference

| Variable | Default | Governs |
|---|---|---|
| `MAVLINK_CONNECTION` | `tcp:127.0.0.1:5760` | Autopilot link (SITL/serial) |
| `HOME_LAT`/`HOME_LON` | 28.6139 / 77.2090 | Home + geofence centre |
| `CRUISE_ALT` / `CRUISE_SPEED` | 15 m / 8 m/s | Defaults per mission |
| `MIN_ALTITUDE`/`MAX_ALTITUDE` | 2 / 120 m | Edge validation bounds |
| `LOW_BATTERY_PCT`/`CRIT_BATTERY_PCT` | 20 / 10 | RTL / LAND demands |
| `GPS_BAD_SAMPLES` | 3 | GPS-loss debounce N |
| `GEOFENCE_RADIUS` | 5000 m | Edge rejection + in-flight RTL |
| `LEG_STALL_TIMEOUT` | 45 s | Progress watchdog |
| `MAX_MISSION_DURATION` | 1800 s | Mission timeout |
| `API_TOKEN` | unset | Write-endpoint auth |
| `MAX_QUEUE_DEPTH` / `HISTORY_LIMIT` | 20 / 1000 | Admission / memory bounds |
| `DB_PATH` | `logs/missions.db` | Persistence |
| `SITL_MODE` | unset | SITL-only pre-arm relaxation gate |

# Appendix C — Test Inventory

**Tier 1 (37 cases, `tests/test_units.py`):** 10 failsafe-arbiter cases
(thresholds, escalation, no-downgrade, debounce ×2, fire-once, geofence,
timeout, healthy baseline); 7 queue cases (priority, depth cap, prune,
cancel ×3, worker bookkeeping); 2 persistence cases (round-trip +
orphan marking, prune); 15 validation cases (coordinate, altitude,
hover, priority, waypoint bounds); 3 configuration cases.

**Tier 2 (`tests/test_full_mission.py`):** eight-property acceptance
flight described in §6.1, runnable on any machine with
`python tests/test_full_mission.py`.
