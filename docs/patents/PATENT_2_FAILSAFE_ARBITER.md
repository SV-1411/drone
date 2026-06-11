# DRAFT — Complete Specification (Indian Patent Office, Form 2 structure)

> **Status and disclaimer.** Draft for review by a registered Indian
> patent agent; not filed, not legal advice. ArduPilot/PX4 firmware
> failsafes are acknowledged prior art — the claims below are directed
> to the *companion-computer arbitration semantics* (debounce,
> non-downgradable severity, mid-recovery escalation, fire-once event
> discipline) layered above and independent of firmware failsafes. An
> official novelty search (IPO InPASS, WIPO PATENTSCOPE) is mandatory
> before filing. Consider filing together with Patent 1 as related
> applications, or merging both into one specification with two
> independent claim families — a call for the patent agent.

---

**FORM 2**
**THE PATENTS ACT, 1970 (39 of 1970)**
**THE PATENTS RULES, 2003**

**COMPLETE SPECIFICATION** (Section 10; Rule 13)

## 1. TITLE OF THE INVENTION

**DEBOUNCED, SEVERITY-ORDERED FAILSAFE ARBITRATION FOR AUTONOMOUS
UNMANNED AERIAL VEHICLE MISSIONS EXECUTED FROM A COMPANION COMPUTER**

## 2. APPLICANT

| | |
|---|---|
| Name | *(to be filled in)* |
| Nationality | Indian |
| Address | *(to be filled in)* |

## 3. PREAMBLE TO THE DESCRIPTION

The following specification particularly describes the invention and the
manner in which it is to be performed.

## 4. FIELD OF THE INVENTION

The invention relates to safety supervision of autonomous UAV missions,
and specifically to a companion-computer failsafe monitor that arbitrates
among a plurality of concurrently evaluated hazard conditions and demands
exactly one recovery action under debounce, severity-ordering, and
escalation rules.

Indicative classifications: G05D 1/00; B64U 2201/10; B64D 45/00 (flight
safety equipment); G08G 5/00.

## 5. BACKGROUND OF THE INVENTION

Autopilot firmware (ArduPilot, PX4) provides individual failsafes —
low-battery return-to-launch (RTL), critical-battery land, geofence
action, ground-station-loss action — each configured and acting largely
independently. Dispatch systems in the patent literature
(US 10,216,181 B2; US 10,089,889 B2; US 12,184,803 B2) presume such
firmware behaviour or simple mission-abort logic.

Three practical deficiencies arise when a companion computer supervises
fully autonomous missions above such firmware. First, *transient sensor
dropouts*: a single corrupted GPS sample, interpreted naively, triggers
an immediate land-in-place — the most disruptive possible action — even
though the fix returns within a second. Second, *severity interaction*:
a low-battery RTL and a later critical-battery land demand interact; a
supervisor that merely records the latest event may downgrade an
in-progress land to a return, or fail to escalate an in-progress return
to a land. Third, *event discipline*: a hazard condition that persists
(battery below threshold persists by definition) re-triggers at the
polling rate, flooding logs and downstream consumers with duplicate
events and obscuring the incident record.

The known art does not disclose a companion-level arbiter combining
per-condition debounce, a monotone severity order over demanded actions,
escalation honoured during an already-commanded recovery, and fire-once
event emission, operating independently of and in addition to firmware
failsafes.

## 6. OBJECTS OF THE INVENTION

- To provide a failsafe supervisor for autonomous UAV missions that
  demands exactly one recovery action at any time, selected under a
  monotone severity order in which a land demand is never downgraded.
- To prevent transient, single-sample sensor anomalies from triggering
  recovery actions, by requiring a configured number of consecutive
  anomalous samples, with recovery of the condition resetting the count.
- To honour severity escalation after a recovery has begun, including
  substituting land for return-to-launch during the return flight.
- To emit each named hazard as a single event per mission, suppressing
  duplicate emission except upon severity escalation.

## 7. SUMMARY OF THE INVENTION

There is provided a failsafe arbitration method executed periodically
(e.g. at 1 Hz) on a companion computer during an autonomous UAV mission,
evaluating a plurality of named hazard conditions — at least battery
level against a low and a critical threshold, satellite-navigation fix
validity, distance from a home location against a geofence radius, and
mission elapsed time against a maximum — and maintaining a single
demanded recovery action with the following properties: (i) each named
condition fires at most once per mission, except that a condition may
re-fire to escalate the demanded action from return-to-launch to land;
(ii) the demanded action is never changed from land to return-to-launch;
(iii) loss of satellite-navigation fix fires only after a configured
number N of consecutive anomalous evaluations, an intervening valid
evaluation resetting the count, and demands land (a return path being
non-navigable without positioning); and (iv) the mission executor
re-evaluates the demanded action within every blocking phase, including
during an already-commanded return, substituting the escalated action
mid-flight. The arbiter operates above unmodified autopilot firmware and
in addition to any firmware failsafes.

## 8. BRIEF DESCRIPTION OF THE ACCOMPANYING DRAWINGS

- **Figure 5** shows the hazard conditions monitored, their thresholds,
  and demanded actions (failsafe tree).
- **Figure 2** shows the mission state machine, including transitions
  from every flight phase to the ABORTED state.
- **Figure 7** shows the arbiter's position as gate 4 of the dispatch
  safety-interlock chain.

(Corresponding to `docs/figures/failsafe_tree.png`, `state_machine.png`,
`safety_interlock.png` of the accompanying implementation; redraw per
Rule 15 for filing.)

## 9. DETAILED DESCRIPTION OF THE INVENTION

### 9.1 Arbiter structure

The arbiter (140) runs as a supervisory thread polling vehicle telemetry
at a fixed cadence during a mission. It holds: a set of named hazard
evaluators (141–144) for battery, positioning, geofence, and elapsed
time; a fired-set recording which named hazards have emitted; a bounded
event list constituting the mission's incident record; and a single
`demanded action` variable taking values from {NONE, RTL, LAND} ordered
NONE < RTL < LAND.

### 9.2 Emission rule

When an evaluator detects its condition, it submits an event carrying a
name, a reason string, and a proposed action. The arbiter accepts the
event iff the name is not in the fired-set, or the proposed action is
LAND while the current demand is RTL (escalation). On acceptance the
event is appended to the incident record and the demanded action is
updated to max(current, proposed) under the severity order — the demand
is therefore monotone non-decreasing within a mission.

### 9.3 Debounced positioning evaluator

The positioning evaluator increments a counter on each evaluation in
which the navigation fix is absent or below a usable fix type, and
resets the counter on any valid evaluation. Only when the counter
reaches a configured threshold N (preferably ≥ 3 consecutive seconds)
does it submit a LAND event. LAND is proposed rather than RTL because a
home-bound trajectory cannot be flown without positioning. The debounce
prevents the costliest recovery action from being taken on a transient
anomaly, while bounding the detection latency to N evaluation periods.

### 9.4 Executor coupling and mid-recovery escalation

The mission executor consults the arbiter inside every blocking loop
(pre-arm wait, climb, transit, hover, return). In particular, the
return-to-launch phase re-reads the demanded action on every iteration;
if the demand has escalated to LAND, the executor commands LAND through
a verified mode-transition routine (described in the related
specification "System and method for verified flight-mode command
delivery…"), abandoning the return. All recovery commands flow through
that verified routine, and the abort path blocks until touchdown and
disarm, as claimed in the related specification.

### 9.5 Best method

The best method known to the applicant is the accompanying open-source
implementation (`flight_core/failsafe_handler.py`,
`flight_core/mission_executor.py`), whose properties are pinned by a
unit suite asserting: RTL on low battery; LAND escalation on critical
battery, including over an in-progress RTL; refusal to downgrade LAND;
no trigger at N−1 anomalous positioning samples and trigger at N; count
reset on recovery; geofence and timeout demands; and single-emission per
named hazard.

### 9.6 Industrial applicability

Applicable to any autonomous UAV operation supervised by a companion
computer, including emergency response, delivery, inspection, and
surveying.

## 10. CLAIMS

**We claim:**

1. A failsafe arbitration method for an autonomous unmanned aerial
   vehicle (UAV) mission, executed periodically on a companion computer
   coupled to an autopilot, the method comprising:
   evaluating a plurality of named hazard conditions including at least
   a battery condition, a satellite-positioning condition, a geofence
   condition, and a mission-duration condition; and
   maintaining a single demanded recovery action over an ordered set
   comprising at least a return action and a land action, the land
   action being of higher severity,
   wherein the demanded action is updated only to an action of equal or
   higher severity, such that a demanded land action is never replaced
   by a return action within the mission.

2. The method of claim 1, wherein each named hazard condition causes at
   most one event emission per mission, a further emission for the same
   name being accepted only where it escalates the demanded action from
   the return action to the land action.

3. The method of claim 1 or 2, wherein the satellite-positioning
   condition is evaluated with a debounce, the condition firing only
   upon a configured number N ≥ 2 of consecutive periodic evaluations
   in which the positioning fix is absent or unusable, an intervening
   valid evaluation resetting the count, and wherein the action proposed
   by said condition is the land action.

4. The method of any of claims 1 to 3, wherein a mission executor
   conducting a return flight commanded by the return action re-reads
   the demanded action periodically during said return and, upon
   escalation to the land action, commands the land action during the
   return flight, abandoning the return.

5. The method of any of claims 1 to 4, wherein the battery condition
   comprises a low threshold proposing the return action and a critical
   threshold proposing the land action, the critical threshold thereby
   escalating an in-progress return commanded by the low threshold.

6. The method of any of claims 1 to 5, wherein every recovery action is
   commanded to the autopilot through a verified mode-transition
   procedure that treats the transition as delivered only upon the
   autopilot's self-reported flight mode matching the commanded mode.

7. A companion-computer system for supervising autonomous UAV missions,
   comprising a processor and memory storing instructions which, when
   executed, perform the method of any of claims 1 to 6, the system
   operating above unmodified autopilot firmware and in addition to any
   failsafe implemented in said firmware.

8. The system of claim 7, wherein accepted events are appended to a
   bounded incident record persisted with the mission, the record
   containing exactly one entry per named hazard per severity level.

## 11. ABSTRACT

**Debounced, severity-ordered failsafe arbitration for autonomous UAV
missions.** A companion-computer supervisor periodically evaluates named
hazard conditions — battery thresholds, satellite-positioning validity,
geofence distance, and mission duration — and maintains a single demanded
recovery action ordered land ≻ return-to-launch. The demand is monotone:
a land demand is never downgraded. Positioning loss is debounced over N
consecutive anomalous samples (reset on recovery) and demands land, since
a return path is non-navigable without positioning. Each named hazard
emits one event per mission, with re-emission only for severity
escalation, keeping the incident record duplicate-free. The mission
executor re-reads the demand inside every flight phase — including an
in-progress return, which is abandoned for a land upon escalation. The
supervisor operates above unmodified autopilot firmware. (Reference:
Figure 5.)

*(Abstract word count ≈ 120.)*

---

*Dated this ____ day of ________ 20__.*
*Signature: ______________________*
*Name of applicant / authorised patent agent: ______________________*
