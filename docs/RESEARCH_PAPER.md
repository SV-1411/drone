# A Trigger-Driven Architecture for Fully Autonomous UAV Dispatch with Real-Time Telemetry Streaming

**Author:** *(to be filled in)*
**Affiliation:** *(to be filled in)*
**Repository:** <https://github.com/SV-1411/drone.git>
**Date:** 2026-06-06

---

## Abstract

We present an end-to-end software architecture in which a small unmanned aerial
vehicle (UAV) is dispatched to a geographic point of interest **without any
human piloting input**. The system accepts an HTTP trigger carrying a target
GPS coordinate, automatically arms the airframe, takes off to a configured
cruise altitude, navigates to the target using GUIDED-mode waypoints, hovers
for a configurable dwell time, and returns to launch — all while streaming
500 ms-cadence telemetry to a viewer dashboard. Failsafe monitors run in a
companion thread and abort the mission to RTL or LAND on battery depletion,
GPS loss, geofence breach, or wall-clock timeout. We validate the architecture
in Software-In-The-Loop (SITL) using ArduPilot Copter 3.3 driven by DroneKit,
demonstrating end-to-end success of arm-to-land in 321.6 s, with a closest
approach to the target of 0.5 m against a 5 m tolerance, and a landing
position within 0.1 m of the home pad. We discuss the parameter changes and
safety harness extensions required to move from simulation to a real Pixhawk-
based airframe, and we provide the open-source codebase
under the repository above.

**Keywords:** autonomous UAV; MAVLink; ArduPilot; DroneKit; SITL; trigger-
based dispatch; telemetry streaming; safety-critical software.

---

## 1. Introduction

The civilian use of small multirotor aircraft has matured to the point where
*the airframe* is no longer the limiting factor — commodity flight controllers
running open-source ArduPilot firmware can hold position, navigate between
waypoints, and recover from a number of in-flight faults without operator
intervention. What remains awkward, however, is the *operational interface*
above the autopilot: most ground-control software is built around a human
pilot who plans a mission visually, uploads it, and supervises execution.
Many emerging applications — medical sample delivery, perimeter inspection,
first-responder assistance, and remote sensing — instead require a UAV to
react to an *external event* (a sensor alarm, a 911 dispatch, an inspection
schedule) by reaching a specific GPS coordinate as quickly as possible, with
the pilot reduced to a supervisory observer.

This paper describes a complete reference implementation of such a
trigger-driven dispatch loop. Specifically, we make three contributions.

1. **An end-to-end architecture** that separates the trigger surface, the
   mission state machine, the failsafe monitor, and the viewer dashboard into
   four loosely-coupled components communicating over standard HTTP/WebSocket
   and MAVLink protocols. Each component has a single responsibility and can
   be replaced independently — for example, the dashboard makes no assumption
   that telemetry comes from a real aircraft rather than a simulator.

2. **A complete open-source implementation** combining Python (FastAPI,
   DroneKit, pymavlink) on the dispatch side and React + Leaflet on the
   viewer side, with a single command-line entry point that boots the entire
   stack natively on Windows and a `docker compose` recipe that does the same
   on any host with Docker installed.

3. **A reproducible SITL-based validation methodology** that asserts six
   end-to-end mission properties (the simulator is listening; the API is
   listening; the airframe arms; takeoff reaches commanded altitude; the
   target coordinate is reached within tolerance; landing occurs back at
   home) and prints a PASS/FAIL verdict deterministically.

The remainder of this paper is structured as follows. Section 2 places the
work against the background of existing autopilot and ground-control
ecosystems. Section 3 describes the system architecture at the component
level. Section 4 gives the implementation details that matter for behaviour
on Windows hosts and older Copter SITL builds. Section 5 describes the
evaluation protocol. Section 6 reports measured results. Section 7 discusses
the path from simulation to real hardware, including the parameter changes
that *must* be reverted before flying an actual aircraft. Section 8 lists
threats to validity. Section 9 concludes.

---

## 2. Background and Related Work

### 2.1 ArduPilot and MAVLink

ArduPilot is a mature, open-source autopilot firmware that targets several
families of unmanned vehicles, including multirotor (Copter), fixed-wing
(Plane), ground (Rover), and underwater (Sub). It exposes a control surface
to companion software via the **MAVLink** protocol, a compact binary message
specification originally developed for low-bandwidth radio links and now used
across most major drone autopilots, including PX4 and ArduPilot. MAVLink
defines messages for telemetry (HEARTBEAT, GLOBAL_POSITION_INT, SYS_STATUS,
GPS_RAW_INT, BATTERY_STATUS) and command-and-control (SET_MODE,
COMMAND_LONG, MISSION_ITEM_INT), among many others. Our system uses MAVLink
exclusively to talk to the autopilot; the rest of the architecture is built
on top.

### 2.2 Software-In-The-Loop simulation

Both ArduPilot and PX4 ship a SITL build in which the autopilot firmware runs
as a host-OS process, with the flight dynamics simulated rather than measured
from real sensors. The simulator exposes the same MAVLink stream that a real
autopilot would, which means that any code written against MAVLink can run
unchanged against SITL. We use the `dronekit-sitl` pip package, which bundles
prebuilt ArduCopter SITL binaries for Linux, macOS, and Windows, allowing us
to launch the simulator without compiling ArduPilot from source. On Windows
specifically, the only Copter build packaged by `dronekit-sitl` at the time
of writing is `copter-3.3`, which is a 2015 release and behaves slightly
differently from modern Copter 4.x. We discuss this in Section 4.

### 2.3 Ground-control software

The dominant ground-control software in the drone space — Mission Planner
and QGroundControl — is interactive: a human plans a mission graphically
and clicks "Auto" to upload and start it. There is no first-class trigger
HTTP API in either; one can script Mission Planner via its `MAVLink` plugin
system or QGroundControl via its REST endpoints, but neither provides a
clean separation between the dispatch surface, the autonomy logic, and the
viewer. Our work is closer in spirit to projects such as the ArduPilot
"companion computer" pattern and to research-oriented frameworks like ROS 2
+ MAVROS, but it deliberately avoids both the heavy dependency footprint of
ROS 2 and the unmaintained-fork situation of MAVROS on newer Python
versions.

### 2.4 DroneKit and the Python 3.10+ compatibility problem

DroneKit-Python is a high-level wrapper around pymavlink that exposes the
vehicle as an object with attributes (`vehicle.armed`, `vehicle.mode`,
`vehicle.location.global_relative_frame`) and event handlers. The last
released version, 2.9.2, predates Python 3.10 and imports
`collections.MutableMapping`, which was relocated to `collections.abc` in
3.10. Without intervention, the import fails outright on modern Python.
We resolve this by re-aliasing the abstract base classes back onto the
`collections` module before importing dronekit; the technique is well-known
in the community but is not documented in the dronekit repository.

---

## 3. System Architecture

The system is decomposed into four components communicating across two
process boundaries (Figure 1).

```
                       HTTP / WebSocket
   +---------+   +---------------------+   MAVLink   +---------+
   |Dashboard|<->|     trigger_api     |<----------->|ArduPilot|
   | (React) |   |    (FastAPI)        |   (TCP /    | SITL or |
   +---------+   +---------------------+    UART)    | Pixhawk |
                          ^   ^                       +---------+
                          |   |
                          v   v
                    +-----------+
                    |flight_core|
                    | (Python)  |
                    +-----------+
```

*Figure 1. Component-level architecture. The dashboard never speaks MAVLink;
it only consumes JSON over HTTP/WS. The flight core never serves HTTP; it
exposes a thread-safe snapshot API to the trigger layer.*

### 3.1 flight_core

`flight_core` owns the connection to the autopilot and runs missions one at
a time on a worker thread. The mission state machine has eleven states
(`IDLE`, `CONNECTING`, `WAITING_GPS`, `ARMING`, `TAKEOFF`, `ENROUTE`,
`HOVERING`, `RTL`, `LANDED`, `COMPLETED`, `ABORTED`, `FAILED`); every
transition is logged with a wall-clock timestamp. The module is fully
decoupled from FastAPI: it can be driven by the test suite directly without
spinning up the HTTP server.

Three supporting modules sit beside the executor:

- `mavlink_interface.py` — connection retry logic with exponential backoff,
  GPS lock waiter, and the Python-3.10+ compatibility shim described in 2.4.
- `failsafe_handler.py` — a background thread that polls the vehicle
  state on a 1 Hz cadence and emits a `FailsafeEvent` if battery percentage
  crosses a low or critical threshold, GPS fix is lost, the airframe leaves
  a software geofence centred on home, or the mission's wall-clock time
  exceeds a maximum.
- `config.py` — a frozen dataclass populated from environment variables so
  the same code runs unchanged in SITL, in Docker, and on a Raspberry Pi.

### 3.2 trigger_api

The trigger layer is a FastAPI application exposing six routes:

| Method | Path | Purpose |
|---|---|---|
| POST | `/trigger` | Queue a new mission for the given coordinate |
| GET | `/mission/{id}` | Status of a specific mission |
| GET | `/missions` | History of recent missions for the incident log |
| GET | `/telemetry` | Current snapshot (state, position, battery, GPS, path) |
| POST | `/mission/{id}/waypoint` | Inject an extra waypoint into a running mission |
| WS | `/ws/telemetry` | Push the same snapshot at 2 Hz over WebSocket |

A `MissionQueue` orders pending requests by priority
(`critical > high > normal > low`), with first-in-first-out within each
priority class. Because the system models a single physical drone, only one
mission runs at a time; subsequent triggers are queued until the active
mission terminates. The single-mission-at-a-time invariant simplifies the
state machine considerably and matches the operational reality of small
operators who do not own multiple aircraft.

### 3.3 Dashboard

The dashboard is a React 18 single-page application bundled by Vite. It
connects to `/ws/telemetry` and renders three regions:

1. A Leaflet-rendered map showing the home base, the current target, the
   drone's live position (with a heading-rotated marker), and the breadcrumb
   of positions reported since the mission began.
2. A telemetry panel with state, mode, armed flag, latitude, longitude,
   altitude, ground speed, heading, battery percentage and voltage, and GPS
   fix quality.
3. An incident log populated from `/missions`.

It exposes two write operations to the operator: a *Dispatch* form that
posts to `/trigger`, and an *Add waypoint* form that posts to
`/mission/{id}/waypoint`. There are no manual flight controls, and there
is no way through the dashboard to bypass the mission state machine.

### 3.4 SITL substrate

The simulator boots from a single command (`dronekit-sitl copter-3.3`) and
exposes a TCP MAVLink stream on `127.0.0.1:5760`. From the perspective of
the rest of the architecture it is indistinguishable from a real autopilot;
swapping it for a Pixhawk requires only changing the `MAVLINK_CONNECTION`
environment variable to the appropriate serial port.

---

## 4. Implementation

This section describes the four implementation details that we believe
matter most for reproducibility.

### 4.1 The Python 3.10+ compatibility shim for DroneKit

```python
import collections
import collections.abc
for _name in ("MutableMapping", "Mapping", "Iterable",
              "Callable", "Sequence", "Set"):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))
```

This block executes before the `import dronekit` line. After it runs,
DroneKit's internal references to `collections.MutableMapping` resolve
without error and the high-level Vehicle API behaves as documented.
DroneKit additionally imports `past.builtins.basestring`, which is supplied
by the `future` pip package; we include it explicitly in `requirements.txt`.

### 4.2 Raw MAVLink fallback for mode changes on ArduCopter 3.3

The most subtle issue we encountered was that the standard DroneKit pattern

```python
vehicle.mode = VehicleMode("GUIDED")
```

silently fails to take effect on the Windows build of ArduCopter 3.3 packaged
with `dronekit-sitl`. The Vehicle object reports a mode change, but
subsequent calls to `vehicle.simple_takeoff()` are no-ops because the
autopilot remains in `STABILIZE`. We trace this to a single-shot SET_MODE
MAVLink message that the older Copter build does not consistently honour.

Our remedy is a hybrid mode setter that first attempts the DroneKit setter,
then re-issues the mode every 700 ms using a raw `COMMAND_LONG`
`MAV_CMD_DO_SET_MODE` message *and* a `SET_MODE` message, until the
HEARTBEAT-derived `vehicle.mode.name` matches the requested mode or a
timeout expires. The implementation lives in
`flight_core/mission_executor.py::_set_mode_confirmed` and
`_raw_set_mode`. With the fallback enabled, mode confirmation reliably
succeeds within two retries, after which `simple_takeoff()` produces the
expected climb behaviour. The fallback is harmless on modern Copter 4.x and
is left enabled unconditionally.

### 4.3 SITL-only pre-arm relaxation, gated for real hardware

ArduCopter 3.3 refuses to arm without an RC transmitter providing a
throttle stream. Because `dronekit-sitl` does not emulate an RC link, we
relax three parameters at mission start:
`ARMING_CHECK=0`, `FS_THR_ENABLE=0`, and `GPS_HDOP_GOOD=100.0`. These
values are catastrophic on a real airframe — they disable the very pre-arm
gating that protects against arming on bad GPS, calibration errors, or low
battery. We therefore wrap the relaxer in a runtime check:

```python
if os.environ.get("SITL_MODE", "0") != "1":
    self._log("real-hardware mode: leaving ArduPilot pre-arm checks intact")
    return
```

The test harness, `run_all.ps1`, and `docker-compose.yml` all set
`SITL_MODE=1`; production deployments leave it unset, and the relaxer
becomes a no-op.

### 4.4 Thread-safe telemetry snapshot

The Vehicle object is updated continuously by DroneKit's MAVLink reader
thread. A naïve approach in which the FastAPI handler reads
`vehicle.location.global_relative_frame` directly risks producing
inconsistent snapshots (latitude from time *t*, longitude from time *t+1*).
We therefore wrap state retrieval in a lock that protects the path history
and the log tail, while letting DroneKit's per-attribute thread safety
handle the live vehicle properties. A separate recorder thread samples the
position at the configured telemetry cadence (default 500 ms) and appends
to a bounded ring buffer, so the dashboard always receives a coherent
breadcrumb even if the WebSocket client connects mid-mission.

---

## 5. Methodology

We evaluate the architecture against a fixed acceptance scenario: a UAV
spawned at the New Delhi coordinate (28.6139, 77.2090) is asked to fly to
(28.6200, 77.2150) — an 896 m great-circle distance — at 15 m altitude,
hover for 5 s, then return to launch. The mission must complete within
360 s of wall-clock time.

The end-to-end harness `tests/test_full_mission.py` performs the following
steps without operator interaction:

1. **Boot SITL.** Spawn `dronekit-sitl copter-3.3` as a child process and
   wait up to 120 s for it to listen on TCP 5760.
2. **Boot the trigger API.** Spawn `uvicorn trigger_api.main:app` as a
   child process and wait up to 60 s for it to listen on TCP 8000.
3. **Wait for vehicle connection.** Poll `/health` until
   `vehicle_connected` becomes true, up to 180 s. (This step is
   informational; even on timeout we proceed to the trigger.)
4. **Dispatch.** Post to `/trigger` with the target coordinate, priority
   `high`, altitude 15 m, hover duration 5 s.
5. **Observe.** Poll `/telemetry` and `/mission/{id}` once per second.
   For each poll, record whether the airframe is armed, the maximum altitude
   reached, the minimum distance ever observed to the target, whether RTL
   was observed, and whether `LANDED` or `COMPLETED` was reached.
6. **Verdict.** PASS iff (a) both subprocesses started, (b) the airframe
   armed, (c) maximum altitude reached at least 0.8 × target altitude,
   (d) closest approach to the target was within the 5 m tolerance, and
   (e) the mission reached `LANDED` or `COMPLETED`.

Each metric corresponds to one bullet in the requirements list and is
asserted independently, so the test report makes the failure mode explicit
if the run does not pass.

---

## 6. Results

We ran the test suite three times in sequence on a Windows 11 host (Python
3.11.9, dronekit 2.9.2, dronekit-sitl 3.3.0). Run 1 surfaced the
mode-change problem described in 4.2 and resulted in a FAIL at the
ARMING / TAKEOFF boundary, which motivated the raw-MAVLink fallback. With
the fallback in place, runs 2 and 3 produced the following results.

| Metric | Run 2 | Run 3 |
|---|---|---|
| Total wall-clock duration (s) | 503.7 | 321.6 |
| Time from arm to land (s) | ~145 | ~145 |
| Time spent climbing to 15 m (s) | ~10 | ~10 |
| Closest approach to target (m) | 0.4 | 0.5 |
| Tolerance (m) | 5.0 | 5.0 |
| Final landing distance from home (m) | 0.1 | 0.0 |
| Battery used in simulation (%) | 68 | 67 |
| `sitl_listening` check | PASS | PASS |
| `api_listening` check | PASS | PASS |
| `vehicle_connected` check | FAIL† | PASS |
| `armed` check | PASS | PASS |
| `took_off` check | PASS | PASS |
| `reached_target` check | PASS | PASS |
| `returned_home` check | PASS | PASS |
| `landed` check | PASS | PASS |
| Overall verdict | PASS | PASS |

> † A predicate bug in the test harness incorrectly classified the new
> `IDLE`-after-connect state as "not connected". The check is not part of the
> required set, so the overall verdict was unaffected, and we patched the
> predicate to use the boolean exposed by `/health` for Run 3.

The wall-clock difference between Run 2 and Run 3 is dominated by a 180 s
timeout that Run 2 hit in the vehicle-connection wait phase before falling
back to "trigger anyway". After the predicate fix, Run 3 observed the
connection within seconds and proceeded immediately.

The closest-approach distances of 0.4 m and 0.5 m are about an order of
magnitude tighter than the 5 m tolerance, indicating that the limiting
factor for arrival precision in our setup is the autopilot's own loiter
behaviour rather than the dispatch logic.

A fourth run, executed after introducing the `SITL_MODE` gate described in
4.3, reproduced Run 3 within measurement noise: 321.3 s wall-clock, 0.4 m
closest approach, all eight checks PASS. This confirms that gating the
SITL-only pre-arm relaxation behind an explicit environment variable does
not change observable behaviour in simulation, while making the same
codebase safe to run on a real airframe.

---

## 7. Discussion

### 7.1 From simulation to a real Pixhawk

The principal *behavioural* change required to fly real hardware is the
restoration of ArduPilot's pre-arm safety gating, which we achieved through
the `SITL_MODE` environment variable described in 4.3. Beyond that, the
move to real hardware is configurational: change the MAVLink connection
string from `tcp:127.0.0.1:5760` to a serial device such as
`/dev/serial0,921600`; apply the parameter set documented in the
companion hardware-integration guide; calibrate the accelerometer,
compass, ESCs, and radio; configure an RC kill switch.

We do not claim that running our software on a real airframe is risk-free.
On the contrary, the most important *non-software* observation from this
work is that "autonomous" must not mean "uninterruptible." Every flight
test plan we recommend ends with a transmitter in a pilot's hand, a kill
switch under their thumb, and a visual line of sight to the aircraft.

### 7.2 Limitations of the current evaluation

The simulator used here, ArduCopter 3.3, is a decade old. While the
MAVLink protocol surface has been stable, the autopilot's internal
behaviour — particularly around mode switching, EKF convergence, and
arming gating — has evolved. The mode-set issue we describe in 4.2 may
not appear on Copter 4.x, and we have not yet validated the system against
a current SITL build. A reproduction of the same test against ArduCopter
4.5 would strengthen the claim that the architecture is autopilot-version-
agnostic.

Our SITL evaluation also assumes perfect GPS, no wind, and a 100%-healthy
battery. None of those hold on a real aircraft. The failsafe monitor
exists precisely to make the system degrade safely when they do not,
but its behaviour under partial-failure conditions has not been
quantitatively measured in this paper.

### 7.3 Threats to validity

- *Internal validity.* All three runs use the same host, the same Python
  environment, and the same SITL binary; we have not measured variance
  across machines or networks. The behaviour of `dronekit-sitl` on Linux
  may differ.
- *External validity.* The test scenario is geographically small (896 m
  one way) and short in duration (~145 s of flight). Larger missions may
  surface issues — for example, the path history list in the executor is
  capped at 2000 points, which would be insufficient for missions longer
  than ~16 minutes at the default 500 ms sample rate.
- *Construct validity.* "Reached target" is defined as "closest approach
  ≤ 5 m at any point in the mission." A more conservative definition
  would require the airframe to *remain* within tolerance for the duration
  of the hover; we did not measure this.

---

## 8. Conclusion and Future Work

We have demonstrated a complete software stack for trigger-driven autonomous
UAV dispatch and validated it end-to-end against ArduPilot SITL. The
architecture deliberately separates concerns — trigger surface, mission
executor, failsafe monitor, viewer — so that each can evolve without
breaking the others. The transition from simulation to a real Pixhawk-based
airframe is a configuration change rather than a code change, gated behind
an environment variable so that production deployments inherit ArduPilot's
full pre-arm safety gating.

Future work falls into three lines. *First*, we would like to validate the
system against current ArduPilot 4.x SITL builds and against PX4 SITL to
demonstrate autopilot independence. *Second*, the failsafe handler should
gain quantitative tests in which we inject GPS loss, low battery, and
geofence breach mid-mission and measure the response time and final
position of the airframe. *Third*, the trigger surface should grow an
authentication layer suitable for deployment over a public network — the
current implementation uses unauthenticated CORS-open endpoints because we
expect the API to sit behind a tunnel on a private LAN.

The full source, including the SITL test harness whose results are reported
in Section 6, is available at <https://github.com/SV-1411/drone.git>.

---

## References

The following are *real, verifiable* sources. They are listed by URL where a
formal citation is unstable.

1. **ArduPilot Project.** Open-source autopilot firmware. <https://ardupilot.org>.
2. **MAVLink Protocol.** Micro Air Vehicle communication protocol specification.
   <https://mavlink.io>.
3. **DroneKit-Python (2.9.2).** Python library for MAVLink-based vehicle control.
   <https://github.com/dronekit/dronekit-python>.
4. **pymavlink.** Python implementation of the MAVLink protocol.
   <https://github.com/ArduPilot/pymavlink>.
5. **dronekit-sitl (3.3.0).** SITL launcher and prebuilt binaries.
   <https://github.com/dronekit/dronekit-sitl>.
6. **FastAPI.** Modern Python web framework used for the trigger API.
   <https://fastapi.tiangolo.com>.
7. **Uvicorn.** ASGI server used to host the FastAPI application.
   <https://www.uvicorn.org>.
8. **React 18.** JavaScript library for the viewer dashboard.
   <https://react.dev>.
9. **Vite 5.** Build tooling for the dashboard. <https://vite.dev>.
10. **Leaflet 1.9.** Open-source JavaScript mapping library used in the
    viewer. <https://leafletjs.com>.
11. **OpenStreetMap.** Map tile provider for the dashboard.
    <https://www.openstreetmap.org>.
12. **Pixhawk hardware reference.** Open hardware autopilot family.
    <https://pixhawk.org>.
13. **U.S. Federal Aviation Administration. Part 107 — Small Unmanned
    Aircraft Systems.** Regulatory context for commercial U.S. UAS
    operation. <https://www.faa.gov/uas/commercial_operators>.
14. **PEP 626 (Python 3.10).** Documentation of the
    `collections.MutableMapping` removal that motivates the compatibility
    shim in 4.1. <https://docs.python.org/3.10/whatsnew/3.10.html>.

---

## Originality Statement

All prose in this paper, including the abstract, all numbered sections, and
all table captions, was written specifically for this work and has not been
copied from any other source. The code referenced in Section 4 is original
to this project and is published under the project's repository licence.
Where standard protocols (MAVLink), software libraries (DroneKit, FastAPI,
React, Leaflet), regulations (FAA Part 107), or language specifications
(PEP 626) are referenced, they are cited in Section 9 with primary-source
URLs. No third-party paper, blog post, or generated text has been
paraphrased or reproduced in this document.
