# DRAFT — Complete Specification (Indian Patent Office, Form 2 structure)

> **Status and disclaimer.** This is a professionally-structured *draft*
> prepared for review by a registered Indian patent agent. It is not legal
> advice and has not been filed. Before filing: (1) run an official
> novelty search (IPO InPASS, WIPO PATENTSCOPE, Google Patents) against
> the claims; (2) decide provisional vs. complete filing; (3) have the
> claims professionally narrowed/broadened. Prior art already identified
> during drafting is disclosed honestly in the Background section —
> the claims are drafted to be distinguishable from it, but only an
> examiner decides.

---

**FORM 2**
**THE PATENTS ACT, 1970 (39 of 1970)**
**THE PATENTS RULES, 2003**

**COMPLETE SPECIFICATION** (Section 10; Rule 13)

## 1. TITLE OF THE INVENTION

**SYSTEM AND METHOD FOR VERIFIED FLIGHT-MODE COMMAND DELIVERY AND
LANDING-INTERLOCKED SERIAL MISSION DISPATCH FOR UNMANNED AERIAL VEHICLES**

## 2. APPLICANT

| | |
|---|---|
| Name | *(to be filled in)* |
| Nationality | Indian |
| Address | *(to be filled in)* |

## 3. PREAMBLE TO THE DESCRIPTION

The following specification particularly describes the invention and the
manner in which it is to be performed.

---

## 4. FIELD OF THE INVENTION

The present invention relates to the field of unmanned aerial vehicle
(UAV) control systems, and more particularly to a companion-computer
system and method that (a) verifies the delivery and adoption of
flight-mode commands issued to an autopilot using the autopilot's own
telemetry stream, with layered command re-encoding on non-confirmation,
and (b) enforces a landing interlock whereby serially dispatched
autonomous missions cannot overlap with an airborne vehicle state.

Indicative classifications: B64U 10/13 (rotorcraft UAVs); B64U 2201/10
(autonomous flight); G05D 1/00 (control of position/attitude of
vehicles); G08G 5/00 (air traffic control / UAV flight management).

## 5. BACKGROUND OF THE INVENTION

Autonomous dispatch of UAVs in response to external triggers is known.
US 10,216,181 B2 discloses a rescue UAV launched by a sensor-generated
trigger toward a recorded GPS position. US 10,089,889 B2 discloses UAV
dispatch initiated from emergency-call events, the UAV self-guiding to
the scene. US 12,184,803 B2 discloses UAV emergency dispatch with
diagnostics reporting. US 9,573,684 B2 and US 10,737,782 B2 disclose
delivery-oriented dispatch-and-return cycles. Open-source autopilot
documentation (ArduPilot, PX4) further establishes firmware-level
failsafes — battery return-to-launch, geofence enforcement, and
ground-station-loss behaviours — as common general knowledge.

The prior art presumes that a command issued to the autopilot is a
command executed. In practice, autopilot firmware may silently reject or
drop a flight-mode change request: the requesting client library can
report success while the autopilot remains in its previous mode. The
present inventor observed this failure empirically on an ArduCopter
software-in-the-loop autopilot, where a high-level mode-change request
to GUIDED mode was reported as accepted by the client while the
autopilot remained in STABILIZE, causing the subsequent takeoff command
to be silently ignored. In an interactive, human-piloted system such a
failure is noticed and corrected by the operator. In an autonomous
dispatch system there is no operator in the loop, and — critically — the
same unverified command pathway is used for *emergency* commands
(return-to-launch, land), where silent non-delivery endangers the
aircraft and third parties.

A second deficiency of the prior art concerns serial mission execution
from a queue. Known dispatch systems treat the termination of mission
*N*'s control logic as sufficient condition to begin mission *N+1*.
Where mission *N* terminates abnormally — by failsafe action or operator
recall — the airframe may still be airborne when mission *N+1* begins
arming and takeoff procedures, producing an undefined and hazardous
vehicle state.

There is accordingly a need for a dispatch system that (i) treats the
autopilot as an unreliable command sink and obtains positive,
telemetry-derived confirmation of every flight-mode transition,
including emergency transitions, with automatic re-encoding of
unconfirmed commands; and (ii) guarantees, as a structural invariant of
the mission queue, that no mission begins while the vehicle is airborne
or armed.

## 6. OBJECTS OF THE INVENTION

It is a principal object of the present invention to provide a UAV
dispatch system in which every flight-mode command, nominal or
emergency, is verified against the autopilot's reported state before
being treated as delivered.

It is a further object to provide layered re-issue of unconfirmed
mode commands through a plurality of protocol encodings, and a
cross-action fallback whereby an unconfirmable emergency action is
substituted by an alternative emergency action.

It is a further object to provide a mission queue whose admission logic
structurally prevents the commencement of a mission against an armed or
airborne vehicle, including after aborted or operator-cancelled
missions.

It is a further object to achieve the foregoing entirely in a companion
computer, without modification of the autopilot firmware.

## 7. SUMMARY OF THE INVENTION

According to a first aspect, there is provided a method of commanding a
flight-mode transition of a UAV autopilot from a companion computer,
comprising: issuing the transition through a first, high-level command
interface; monitoring the autopilot's periodic telemetry (HEARTBEAT)
stream for the autopilot's self-reported flight mode; and, while the
reported mode differs from the commanded mode and a timeout has not
elapsed, periodically re-issuing the transition through at least a
second encoding comprising a MAVLink COMMAND_LONG message carrying
MAV_CMD_DO_SET_MODE and a third encoding comprising a MAVLink SET_MODE
message; the transition being treated as delivered only upon telemetry
confirmation.

According to a second aspect, where the commanded transition is an
emergency action (return-to-launch or land) and confirmation is not
obtained within the timeout, the method substitutes the alternative
emergency action and repeats the verification procedure.

According to a third aspect, there is provided a mission dispatch
system comprising a bounded priority queue and a mission executor,
wherein: every abort path of the executor — failsafe-initiated,
operator-initiated, or exception-initiated — blocks until the vehicle
reports a disarmed state (or a bounded period elapses) before control
returns to the queue; and the executor refuses to commence any mission
while the vehicle reports an armed state; whereby the system maintains
the invariant that no mission is commenced against an airborne vehicle.

According to a fourth aspect, the system rejects, at its network edge,
any dispatch target or in-flight waypoint lying outside a configured
geofence centred on the home location, converting what would otherwise
be an in-flight abort into a pre-flight validation error.

## 8. BRIEF DESCRIPTION OF THE ACCOMPANYING DRAWINGS

- **Figure 1** shows the component architecture of the system (dispatch
  surface, mission executor, failsafe monitor, viewer, autopilot).
- **Figure 2** shows the mission state machine of the executor.
- **Figure 3** shows the message sequence of a dispatched mission.
- **Figure 7** shows the five-gate safety interlock chain from network
  trigger to landing, including the abort guarantee.

(Figures correspond to rendered files of the accompanying
implementation. Figure 2 corresponds to
`docs/figures/v2/fig5_state_machine.png`, which now shows the
thirteen-state machine including the DELIVERING payload phase;
Figure 7 corresponds to `docs/figures/v2/fig6_interlock.png`.
Figures 1 and 3 correspond to the v1 renders
`docs/figures/architecture.png` and `sequence.png` respectively; a
refreshed v2 figure set exists at `docs/figures/v2/`. For filing all
figures are to be redrawn per Rule 15 drawing requirements.)

## 9. DETAILED DESCRIPTION OF THE INVENTION

### 9.1 System context

The system executes on a companion computer (100) communicatively
coupled to a UAV autopilot (200) over a MAVLink transport — serial UART
on a physical aircraft or TCP in simulation. The companion computer
hosts: a network-facing trigger interface (110) accepting dispatch
requests carrying a target coordinate, priority, and optional altitude
and dwell parameters; a bounded priority queue (120); a mission executor
(130) implementing a finite state machine over the states IDLE,
CONNECTING, WAITING_GPS, ARMING, TAKEOFF, ENROUTE, HOVERING, RTL,
LANDED, COMPLETED, ABORTED, FAILED; and a failsafe monitor (140)
described in the co-filed specification "Companion-computer failsafe
arbitration…".

### 9.2 Verified mode-transition protocol (the "confirmed setter")

All mode transitions are routed through a single routine (132). The
routine first issues the transition through the high-level client
interface. It then enters a confirmation loop bounded by a timeout
(typically 10–15 s): on each iteration it reads the flight mode most
recently reported by the autopilot's HEARTBEAT-derived telemetry. If
the reported mode equals the commanded mode, the routine returns
success. Otherwise, at a re-issue interval (typically 700 ms) it
transmits the transition redundantly as (a) a COMMAND_LONG message
carrying MAV_CMD_DO_SET_MODE with the custom-mode identifier resolved
from the autopilot's mode mapping, and (b) a SET_MODE message, and (c)
re-invokes the high-level interface. Because mode-set requests are
idempotent, redundant issuance is harmless; because confirmation is
read from the autopilot's own report, no client-side state is trusted.
(Formally: with confirmation window T ∈ [10, 15] s and re-issue
interval δ = 0.7 s, the routine performs at most ⌈T/δ⌉ ≈ 21 layered
re-issues before the cross-action fallback (134), described in the
following paragraph, engages.)

On timeout the routine returns failure. For nominal transitions the
caller raises a mission failure (handled in §9.4). For emergency
transitions the caller applies the cross-action fallback (134): if RTL
cannot be confirmed, LAND is commanded through the same verified
routine, and vice versa, on the rationale that *some* confirmed
recovery action is preferable to an optimal but unconfirmed one.

### 9.3 Landing-interlocked queue

The queue (120) is bounded (excess requests refused at admission) and
strictly serial. The interlock comprises two cooperating mechanisms:

(a) **Abort guarantee (136).** Every path by which a mission terminates
abnormally — failsafe action, operator recall via the network interface,
or unhandled exception with the vehicle airborne — commands its recovery
action through the verified routine of §9.2 and then blocks, polling
vehicle telemetry, until the vehicle reports disarmed with near-zero
relative altitude, or a bound (typically 240 s) elapses. Only then does
control return to the queue worker.

(b) **Pre-flight interlock (138).** Upon dequeuing a mission, the
executor reads the vehicle's armed flag. If armed, it waits up to a
bound (typically 120 s) for disarm; failing that, the mission is failed
without any arming or takeoff command being issued.

Mechanisms (a) and (b) jointly establish the invariant that the queue
never commences a mission against an airborne vehicle: (a) makes
violation improbable, (b) makes it impossible.

### 9.4 Edge geofence validation and recall

The trigger interface validates each dispatch target and each in-flight
waypoint against a geofence radius centred on the home location,
rejecting non-compliant requests with a client error before any flight
activity. A recall endpoint removes a queued mission atomically or, for
a running mission, sets an abort flag observed by every blocking phase
of the executor, which then routes into the abort guarantee of §9.3(a).

### 9.5 Best method

The best method presently known to the applicant is the open-source
implementation accompanying this draft (Python 3.11 companion-computer
stack; FastAPI trigger surface; the verified setter implemented over
DroneKit and pymavlink; ArduPilot autopilot), validated by a 37-case
unit suite and end-to-end software-in-the-loop acceptance flights
achieving 0.4–0.6 m terminal accuracy and 8/8 acceptance checks.

### 9.6 Industrial applicability

The invention is applicable to emergency-response UAV dispatch, medical
delivery, perimeter inspection, and any application requiring unmanned
serial missions launched by machine-generated triggers.

## 10. CLAIMS

**We claim:**

1. A method of commanding a flight-mode transition of an unmanned
   aerial vehicle (UAV) autopilot from a companion computer, the method
   comprising:
   (a) issuing a mode-transition request through a first command
   interface;
   (b) monitoring a telemetry stream periodically emitted by the
   autopilot for the autopilot's self-reported flight mode;
   (c) while the self-reported flight mode differs from the requested
   mode and a confirmation timeout has not elapsed, re-issuing the
   request at a re-issue interval through at least one further protocol
   encoding distinct from the first command interface; and
   (d) treating the transition as delivered only upon the self-reported
   flight mode matching the requested mode,
   wherein the at least one further encoding comprises a MAVLink
   COMMAND_LONG message carrying MAV_CMD_DO_SET_MODE.

2. The method of claim 1, wherein the at least one further encoding
   additionally comprises a MAVLink SET_MODE message, the request being
   issued redundantly through a plurality of encodings within each
   re-issue interval.

3. The method of claim 1 or 2, wherein the requested mode is an
   emergency recovery mode selected from return-to-launch and land, and
   wherein, upon elapse of the confirmation timeout without delivery,
   the method further comprises commanding the other of return-to-launch
   and land through steps (a)–(d).

4. A mission dispatch system for a UAV, comprising a network-facing
   trigger interface, a bounded mission queue executing missions
   serially, and a mission executor coupled to an autopilot, wherein:
   (a) every abnormal-termination path of the executor commands a
   recovery flight mode by the method of any of claims 1 to 3 and
   thereafter blocks until the vehicle reports a disarmed state or a
   bounded wait elapses, before control returns to the queue; and
   (b) the executor, upon receiving a mission from the queue, refuses to
   issue arming or takeoff commands while the vehicle reports an armed
   state;
   whereby no mission is commenced against an airborne vehicle.

5. The system of claim 4, wherein the trigger interface rejects, prior
   to queue admission, any dispatch target lying outside a configured
   geofence centred on a home location of the vehicle, and rejects any
   in-flight waypoint request lying outside said geofence.

6. The system of claim 4 or 5, further comprising a recall interface
   which, for a queued mission, removes the mission from the queue
   atomically, and, for an executing mission, sets an abort indication
   observed by every blocking phase of the executor, the executor
   thereupon performing the abnormal-termination path of claim 4(a).

7. The system of any of claims 4 to 6, wherein upon a shutdown request
   received while the vehicle reports an armed state, the system
   commands return-to-launch by the method of any of claims 1 to 3
   before releasing its communication link with the autopilot.

8. The system of any of claims 4 to 7, implemented entirely on a
   companion computer without modification of the autopilot firmware.

## 11. ABSTRACT

**Verified flight-mode delivery and landing-interlocked dispatch for
UAVs.** A companion-computer dispatch system treats the autopilot as an
unreliable command sink: every flight-mode transition — including
emergency return-to-launch and land — is issued through a high-level
interface and re-issued through redundant MAVLink encodings
(COMMAND_LONG/MAV_CMD_DO_SET_MODE and SET_MODE) until the autopilot's
own HEARTBEAT-derived telemetry confirms adoption, with a cross-action
fallback substituting land for return-to-launch (or vice versa) when
confirmation fails. A serial mission queue enforces a landing interlock:
all abort paths block until the vehicle reports disarmed, and no mission
may begin while the vehicle is armed, so that no dispatched mission can
commence against an airborne vehicle. Targets outside a configured
geofence are rejected before flight. (Reference: Figure 7.)

*(Abstract word count ≈ 120.)*

---

*Dated this ____ day of ________ 20__.*
*Signature: ______________________*
*Name of applicant / authorised patent agent: ______________________*
