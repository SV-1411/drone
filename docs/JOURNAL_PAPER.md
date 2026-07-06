# VanniKawachh: A Distributed AI Acoustic Intelligence and Autonomous Drone Response Network for Women Safety

**Shivansh Verma, Saksham Sabadra, Rudra Thakur, Rohan Untawale**

*Department of Computer Science and Engineering, G H Raisoni College of Engineering, Nagpur, India*

**Guide: Dr. Aditya Turankar**, Assistant Professor, Department of Computer Science and Engineering, G H Raisoni College of Engineering, Nagpur, India

---

## Abstract

Most crimes against women occur precisely where existing safety technology fails: dark streets, forest paths, and no-signal parking areas. Prevailing solutions shift the burden of safety onto the potential victim, who must carry a device, install an application, keep it charged, and reach for it at the worst possible moment. VanniKawachh removes that burden. Solar-powered microphone nodes mounted on poles listen continuously for acoustic distress events ("Bachao!", "Help!", screams). A two-stage artificial-intelligence pipeline keeps false alarms low: each node's ESP32-S3 microcontroller screens every second of audio with a lightweight MFCC-plus-CNN classifier (Stage 1, under 50 ms per frame), and a Raspberry Pi 5 hub confirms candidate events with PANNs deep audio analysis fused with motion, ambient-light, and time-of-day evidence (Stage 2). Confirmed alerts—AES-128 encrypted and carrying the node's surveyed GPS coordinates—travel over LoRa, requiring no SIM card or cellular coverage, to a police dashboard, and simultaneously auto-dispatch a Pixhawk quadcopter that records evidence at the scene and delivers a first-aid kit. The response chain is protected by a safety framework comprising telemetry-verified flight-mode delivery, a debounced severity-ordered failsafe arbiter, and a landing-interlocked mission queue. We present the system architecture, the cryptographic alert protocol, and the flight-safety framework, validated by software-in-the-loop acceptance flights (8/8 checks passed, 0.4 m terminal accuracy), 68 automated unit verifications, and a complete end-to-end chain rehearsal from sealed alert to payload release. Her voice is the only safety device she needs.

**Keywords** — women's safety, acoustic event detection, MFCC, CNN, PANNs, LoRa, AES encryption, GPS, autonomous quadcopter, Pixhawk

---

## I. Introduction

Public-safety statistics and case studies repeatedly show that violent crimes against women concentrate in locations with poor infrastructure coverage: unlit streets, isolated stretches between transit stops, forest and campus peripheries, and underground or remote parking areas. These are exactly the locations where the two dominant classes of safety technology break down. Cellular-network-dependent applications lose connectivity; camera surveillance requires lighting, power, and a human observer; and personal devices require the victim to possess, charge, and physically operate them during an assault.

This last point deserves emphasis, because it is a structural flaw rather than an engineering one. Nearly every deployed women-safety solution—smartphone applications, smart wearables, GPS panic buttons—implements a *victim-carried* trigger. The system works only if the woman (i) owns the device, (ii) is carrying it, (iii) has kept it charged, (iv) has network coverage, and (v) can reach and operate it during the seconds in which an attack unfolds. Each condition is individually plausible and jointly fragile. Reported detection accuracies of such devices exceed 97% [5], yet the accuracy is conditioned on the device being present and usable—a condition the threat model itself undermines, since an assailant's first action is often to separate the victim from her phone.

VanniKawachh ("Vanni" — voice; "Kawachh" — shield) inverts the responsibility. The sensing infrastructure is mounted on public poles, powered by solar energy, and listens continuously; the victim carries nothing. Her voice—a scream, a cry, the keywords "help" or "bachao"—is the trigger. Detection, verification, alerting, and physical first response are all performed by fixed and aerial infrastructure.

The contributions of this paper are:

1. **An end-to-end architecture** for infrastructure-mounted acoustic women-safety sensing, spanning solar-powered ESP32-S3 sensing nodes, a Raspberry Pi 5 verification hub, and an autonomous Pixhawk quadcopter response layer, in which no component depends on cellular coverage or a victim-carried device.
2. **A two-stage acoustic verification pipeline** that pairs a recall-tuned, sub-50 ms on-node MFCC+CNN screen with a precision-tuned hub stage combining PANNs [13] deep audio tagging and a weighted fusion of PIR motion, ambient light, and time-of-day evidence, including a defined degraded-mode path when the verification clip cannot be delivered.
3. **A 25-byte authenticated alert protocol** for LoRa, using AES-128-CTR confidentiality, truncated HMAC-SHA256 authenticity, per-node key derivation from a single master key, and monotonic-counter replay protection—sized to a single LoRa frame and designed around the observation that a spoofed packet would launch an aircraft.
4. **A safety-verified autonomous response framework** for the dispatch drone: telemetry-confirmed flight-mode delivery with layered MAVLink re-encoding and cross-action emergency fallback; a landing-interlocked serial mission queue; a debounced, severity-ordered failsafe arbiter; geofence validation at the network edge; and a payload-delivery phase whose failure mode is return-to-launch, never loiter. These mechanisms are the subject of two patent applications in preparation.
5. **Software-in-the-loop (SITL) validation** of the complete response chain—8/8 acceptance checks, 0.4 m terminal accuracy, 68 automated unit verifications, and a full-chain rehearsal from sealed alert packet to simulated first-aid drop—together with an honest statement of which measurements remain pending on physical hardware.

The remainder of the paper is organized as follows. Section II surveys related work and identifies the gap VanniKawachh addresses. Section III presents the three-tier architecture. Sections IV–VI detail the acoustic verification pipeline, the secure alerting protocol, and the flight-safety framework respectively. Section VII reports experimental results and explicitly delimits validated claims from pending measurements. Section VIII discusses privacy, regulatory context, and limitations. Section IX concludes.

## II. Related Work

Prior work on technology for women's safety and acoustic distress detection falls into two broad categories: systems the victim must carry, and systems that detect but do not respond.

### A. Victim-Carried Devices and Applications

Pavithra et al. [1] present a discreet smartphone application with on-device audio recognition and emergency automation; the design is thoughtful, but the trigger chain still requires the victim's own charged, network-connected phone. Bharathi et al. [5] describe an IoT wearable combining GPS and accelerometer sensing, reporting 97.54% detection accuracy, a 3.2 s response time, and a 1.92% false-positive rate—strong figures that nonetheless apply only while the wearable is worn and charged. Snehith et al. [6] and Hadkar et al. [9] present IoT safety devices in which a push-button or wearable initiates locate-and-alert behaviour; both require manual triggering by the victim. Uganya et al. [10] describe a button-triggered GSM/GPS tracker, which is inoperative exactly in the GSM dead zones where risk is highest. Potturi et al. [11] automate the SOS trigger with GSM/GPS geo-location sharing but retain both the carried-device and cellular-coverage dependencies. Across this category, reported accuracies are high, but the burden of possession, charge, coverage, and reach remains on the victim.

### B. Detection-Only Acoustic Systems

A second body of work detects distress sounds without providing location delivery or physical response. Kim et al. [7] built an 11,921-sample large-scale scream dataset and found a CNN-Transformer to be the best of five evaluated models; the system is server-scale and terminates at detection. The same group [2] later proposed a CNN-Transformer with a windowing CNN for scream temporal-interval prediction, improving F-measure by roughly three percentage points and equal-error rate by an order of magnitude—but the model is compute-heavy and not deployable on low-power field nodes. Sharma and Jebaseeli [3] report a scream-and-panic detector at 92% accuracy with under 5% false positives and 4–6 s response, bound to the user's device. Srimathi et al. [4] show that scream detection can reduce reaction time by 40% and increase intervention rates by 30%, underscoring the operational value of acoustic sensing, but their system is single-stage and offers no field response. Fime et al. [8] achieve 95.51% danger-sound accuracy with Noisereduce preprocessing and InceptionV3, identifying MobileNetV2 as a lighter alternative—again, detection only. Ciaburro and Puyana-Romero [12] systematically review sound-event detection in smart cities and confirm both the maturity of detection methods and the near-absence of closed-loop response systems in the literature.

### C. The Gap

Table I summarizes the pattern. Victim-carried systems close the response loop but place the trigger burden on the victim; detection-only systems remove that burden but stop at a classification score. To the best of our knowledge, no prior system provides the complete chain of *infrastructure-mounted sensing* (no victim burden), *verified low-false-alarm alerting that operates offline* (no cellular dependency), and *autonomous physical field response* (aid arrives before ground units). VanniKawachh is designed to fill exactly this gap.

**Table I. Positioning of VanniKawachh against prior work**

| Property | Victim-carried [1], [5], [6], [9], [10], [11] | Detection-only [2], [3], [4], [7], [8] | VanniKawachh |
|---|---|---|---|
| Victim must carry/charge a device | Yes | No | No |
| Works without cellular coverage | Mostly no | N/A (server-side) | Yes (LoRa) |
| Deployable on low-power field nodes | Yes | Mostly no | Yes (two-stage split) |
| False-alarm suppression stage | No | Single-stage | Two-stage + sensor fusion |
| Location delivered to responders | Yes (live GPS) | No | Yes (surveyed registry) |
| Autonomous physical response | No | No | Yes (quadcopter) |

## III. System Architecture

VanniKawachh comprises three tiers: per-pole sensing nodes, a per-locality hub, and a response drone. The design principle uniting all three is that *a detection claimed is not a detection confirmed*—every layer independently verifies before it acts, whether the object of verification is a sound, a network packet, or a flight-mode command.

### A. Tier 1: Sensing Node

Each node is a weatherproof, solar-powered unit (ESP32-S3 microcontroller; INMP441 I2S MEMS microphone sampling 16 kHz mono; HC-SR501 PIR motion sensor; LDR ambient-light sensor; SX1278 LoRa transceiver at 433 MHz; 18650 Li-ion cell with TP4056 charging from a 5 V solar panel). The ESP32-S3 continuously frames incoming audio, extracts MFCC features, and runs a lightweight convolutional classifier under TensorFlow Lite for Microcontrollers [14], budgeted at under 50 ms per frame. Audio that does not resemble distress is discarded on-device—nothing is stored and nothing is transmitted. On a Stage-1 hit, the node (i) transmits a sealed 25-byte alert over LoRa (Section V) and (ii) uploads a 4 s verification clip over ESP-NOW/WiFi to the hub. Nodes carry no GPS: each pole is surveyed once at installation, and position is resolved at the hub from a `node_id → (lat, lon)` registry. A node therefore has no live position fix to spoof, jam, or drain.

### B. Tier 2: Hub

The hub is a Raspberry Pi 5 serving one locality. A gateway ESP32 with an SX1278 receives LoRa frames and bridges them to the Pi over USB serial; the gateway performs no cryptography or parsing, so all security-relevant logic remains on the Pi where it can be updated without reflashing field hardware. The hub authenticates and decrypts each alert, checks the replay counter, looks up the node registry, waits a bounded time for the verification clip, runs Stage-2 audio analysis (PANNs [13]), fuses the result with the alert's PIR/light flags and the time of day (Section IV), and—only above configured thresholds—dispatches the drone by an HTTP POST to the flight stack's trigger interface while raising the incident on a police-facing dashboard with a live map and alarm.

### C. Tier 3: Response Drone

The response layer is a Pixhawk 2.4.8 quadcopter (F450 class) with an onboard companion computer running the flight stack: a FastAPI trigger interface with a bounded priority queue, a 13-state mission executor (IDLE, CONNECTING, WAITING_GPS, ARMING, TAKEOFF, ENROUTE, HOVERING, DELIVERING, RTL, LANDED, COMPLETED, ABORTED, FAILED), a 1 Hz failsafe arbiter, and obstacle keep-out routing. The drone flies to the node's surveyed coordinates in GUIDED mode over MAVLink [15], records camera evidence during hover, descends to release a first-aid kit, and returns to launch. The complete safety machinery is described in Section VI.

### D. Methodology Flow

Fig. 1 traces one incident through the system.

```
                    victim shouts ("Bachao!" / "Help!" / scream)
                                      |
                                      v
                 INMP441 microphone, 24x7 capture (16 kHz I2S)
                                      |
                                      v
              Stage 1: MFCC + CNN on ESP32-S3  (< 50 ms / frame)
                                      |
                            distress-like event?
                             /                \
                          no/                  \yes
                           v                    v
                   keep listening      Stage 2: PANNs deep audio
                 (frame discarded,     analysis + PIR/LDR/time-of-day
                  nothing stored)      sensor fusion on Raspberry Pi 5
                                                |
                                       genuine distress?
                                        /             \
                                     no/               \yes
                                      v                 v
                              discard + log     AES-128-sealed alert
                                                + surveyed GPS coords
                                                        |
                                                        v
                                          LoRa uplink (5-10 km class,
                                           no SIM, no cellular)
                                                        |
                                     +------------------+------------------+
                                     v                                     v
                            police dashboard                    drone auto-dispatch
                          (live map + alarm)                     (POST /trigger)
                                                                            |
                                                                            v
                                                              autonomous waypoint flight
                                                                            |
                                                                            v
                                                                  evidence recording
                                                                            |
                                                                            v
                                                                   hover and monitor
                                                                            |
                                                                            v
                                                                  first-aid kit drop
                                                                   (from <= 3 m)
                                                                            |
                                                                            v
                                                                  return to launch (RTL)
```

*Fig. 1. VanniKawachh methodology flow from acoustic event to autonomous response.*

## IV. Two-Stage Acoustic Verification

The acoustic pipeline is split across the node and the hub because the two requirements—never miss a real event, and never launch on a false one—pull in opposite directions and are best served by different operating points on different hardware.

### A. Stage 1: Recall-Tuned On-Node Screening

The node computes MFCCs over short frames of the 16 kHz microphone stream and classifies them with a compact CNN of the `micro_speech` class under TensorFlow Lite for Microcontrollers [14], targeting scream, cry, and the keywords "help" and "bachao". The stage is deliberately *recall-tuned*: its purpose is to not miss distress, and its false positives are cheap because Stage 2 filters them at the hub. The latency budget is under 50 ms per frame so that the node keeps pace with real time on the ESP32-S3's resources. In the current prototype, the deployed Stage-1 classifier is a calibrated energy/band heuristic standing in for the trained TFLM model; model training on scream/keyword corpora is scheduled as Phase 1 of the build plan (Section VII-D).

### B. Stage 2: Precision-Tuned Hub Verification

The hub scores the 4 s verification clip with PANNs [13], a family of large-scale pretrained audio neural networks trained on AudioSet. The distress score is the summed clipwise probability over the distress-relevant AudioSet classes (screaming, shouting, yelling, crying, wailing, groaning, whimpering), yielding a value in [0, 1]. CNN14 is the default checkpoint, with CNN10 or a MobileNet variant as substitutes if inference on the Pi 5 proves too slow. The verifier also implements an energy-heuristic fallback backend (loudness, spectral centroid, and envelope burstiness) so that the full pipeline remains executable and testable on machines without PyTorch; this fallback is explicitly not a claim of detection accuracy and is labelled as such wherever results are reported.

### C. Evidence Fusion

A night-time scream in a dark spot with motion nearby warrants a different response from a daytime shout on a busy road. The hub therefore fuses the Stage-2 audio score with environmental evidence carried in the alert packet. With `a` the Stage-2 audio score, `c` the Stage-1 confidence, `m ∈ {0,1}` the PIR motion flag, `L ∈ [0,255]` the LDR light level, and `h` the local hour of day, the fused severity is

> S = 0.60·a + 0.15·c + 0.10·m + 0.08·d + 0.07·n

where darkness `d = 1 − L/255` and the night indicator `n = 1` if `h ≥ 20` or `h < 6`, else 0; `S` is clamped to [0, 1]. Audio evidence dominates (weight 0.60), while each contextual factor nudges severity upward. Mission priority is set to *high* when `S ≥ 0.75`, or when `a ≥ 0.6` with motion confirmed (`m = 1`); otherwise *normal*. Dispatch requires both gates to pass: `a ≥ θ_verify` and `S ≥ θ_dispatch`. Alerts below threshold are logged for audit but do not launch the drone; this gating is pinned by unit tests. The weights are prototype values to be tuned against Phase-1 bench data.

### D. Degraded Path: Missing Clip

LoRa carries the alert but cannot carry audio (Section V), so Stage 2 depends on the ESP-NOW/WiFi clip arriving. If no clip arrives within a bounded wait, the hub does not silently drop the incident: it substitutes a degraded audio score of `a = 0.6·c` (the Stage-1 confidence at a haircut) and proceeds through fusion and gating. In practice this means a low-confidence event without a clip will be logged but not dispatched, while a very-high-confidence Stage-1 event may still dispatch at reduced confidence. Multi-node corroboration—raising confidence when neighbouring nodes report the same event—is identified as future work in this path.

## V. Secure Offline Alerting

### A. Threat Model

The alert channel commands the launch of an autonomous aircraft. A forged packet would dispatch a drone to an arbitrary location; a replayed packet would re-dispatch it; an eavesdropped packet would reveal that (and where) an incident is in progress. The protocol therefore provides confidentiality, authenticity, and replay protection on every packet, under the constraint that the whole message must fit comfortably in one LoRa frame at high spreading factors.

### B. Packet Format

Every alert is a fixed 25-byte packet (Table II).

**Table II. VanniKawachh LoRa alert wire format (25 bytes)**

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 2 | Magic `"VK"` | cleartext |
| 2 | 1 | Version (1) | cleartext |
| 3 | 2 | `node_id` (uint16, BE) | cleartext — selects the per-node key |
| 5 | 4 | `counter` (uint32, BE) | cleartext — CTR nonce material + replay check |
| 9 | 8 | Ciphertext of payload | AES-128-CTR |
| 17 | 8 | MAC | HMAC-SHA256(node key, header ∥ ciphertext), truncated to 8 bytes |

The 8-byte encrypted payload carries: event class (1 = scream, 2 = help-keyword, 3 = cry, 4 = crash), Stage-1 confidence quantized to 0–255, PIR flag, LDR light level (0–255), node battery percentage, and three reserved bytes.

### C. Cryptographic Construction

Confidentiality is provided by AES-128 [17] in CTR mode, with the 16-byte counter block derived from the cleartext header (magic, version, node ID, counter), which is unique per packet as long as the per-node counter is monotonic. Authenticity is provided by HMAC-SHA256 over the header and ciphertext, truncated to 8 bytes—an encrypt-then-MAC construction verified before decryption with a constant-time comparison. Each node's key is derived from a single master key as

> K_node = HMAC-SHA256(K_master, "node:" ∥ node_id)[0:16]

so provisioning a new node requires only the master key and an assigned ID, and compromise of one node's key does not reveal the master key or any sibling key. Replay protection uses the monotonic per-node counter: the hub persists the last accepted counter per node and rejects any packet whose counter does not strictly increase. Packets with an unknown `node_id`, a failed MAC, a stale counter, or a malformed length are dropped and logged. All of these rejection behaviours—tampered MAC, replayed counter, unknown node—are pinned by automated tests.

### D. Why LoRa, and Why the Audio Travels Separately

LoRa's effective throughput at usable range is roughly 1–5.5 kbps, which cannot carry even heavily compressed audio in useful time, but delivers a 25-byte alert essentially instantly at ranges of the 5–10 km class in open terrain (to be measured for our deployment in Phase 2). The design therefore splits the two flows: the *alert* travels over LoRa with no SIM or cellular dependency, while the 4 s *verification clip* travels over ESP-NOW/WiFi (~250 kbps, hundreds of metres line-of-sight) to the hub. The alert path is the safety-critical one and has no dependency on the clip path; if the clip is lost, the degraded-score path of Section IV-D applies. The LoRaWAN specification [16] documents the underlying modulation and regional parameters; the prototype uses raw LoRa point-to-point framing rather than a full LoRaWAN network stack, since each node speaks only to its own hub.

## VI. Safety-Verified Autonomous Response

The response tier is where a software error stops being a bug and becomes a hazard to people on the ground. The flight stack therefore treats the autopilot as an *unreliable command sink* and enforces safety as a set of structural invariants in the companion computer, above and in addition to the autopilot firmware's own failsafes. The mechanisms in this section are the subject of two patent applications in preparation.

### A. Verified Flight-Mode Delivery

Autopilot firmware may silently reject or drop a flight-mode change: the client library reports success while the autopilot remains in its previous mode. We observed this empirically on an ArduCopter SITL autopilot, where a GUIDED-mode request was reported accepted while the vehicle remained in STABILIZE, causing the subsequent takeoff command to be silently ignored. In a human-piloted system an operator notices and retries; in an autonomous system there is no operator—and the same unverified pathway carries the *emergency* commands (RTL, LAND).

All mode transitions therefore flow through a single verified setter. It issues the transition through the high-level client interface, then enters a confirmation loop bounded by a timeout (10–15 s): on each iteration it reads the flight mode the autopilot itself reports in its HEARTBEAT-derived telemetry. Until the reported mode matches, it re-issues the command at a ~700 ms interval through *layered protocol encodings*: a MAVLink `COMMAND_LONG` carrying `MAV_CMD_DO_SET_MODE` with the resolved custom-mode identifier, a MAVLink `SET_MODE` message, and the high-level interface again. Mode-set requests are idempotent, so redundant issuance is harmless; because confirmation is read from the autopilot's own report, no client-side state is trusted. A transition is treated as delivered *only* upon telemetry confirmation.

### B. Cross-Action Emergency Fallback

If an emergency transition cannot be confirmed within the timeout, the executor substitutes the alternative emergency action through the same verified routine: an unconfirmable RTL becomes a LAND command, and vice versa. The rationale is that some *confirmed* recovery action is preferable to an optimal but unconfirmed one. One asymmetry is enforced: a LAND demand is never downgraded to RTL.

### C. Landing-Interlocked Serial Dispatch

Missions are executed strictly serially from a bounded priority queue, and the queue maintains the invariant that *no mission ever begins against an airborne vehicle*, via two cooperating mechanisms. First, the **abort guarantee**: every abnormal-termination path—failsafe action, operator recall, or unhandled exception with the vehicle airborne—commands its recovery mode through the verified setter and then blocks, polling telemetry, until the vehicle reports disarmed at near-zero relative altitude (bounded at 240 s) before control returns to the queue worker. Second, the **pre-flight interlock**: on dequeuing a mission, the executor reads the vehicle's armed flag and, if armed, waits up to 120 s for disarm; failing that, the mission is failed without a single arming or takeoff command being issued. The first mechanism makes violation improbable; the second makes it impossible.

### D. Failsafe Arbiter

A supervisory thread polls vehicle telemetry at 1 Hz throughout the mission, evaluating named hazard conditions: battery against a low threshold (demands RTL) and a critical threshold (demands LAND), GPS fix validity, geofence distance from home, mission wall-clock duration, MAVLink heartbeat staleness, and per-leg navigation progress (stall detection). The arbiter maintains a single demanded action over the ordered set NONE < RTL < LAND with three disciplines:

- **Debounce.** GPS loss fires only after N consecutive anomalous 1 Hz samples (N = 3 by default), with any valid sample resetting the count—a single corrupted sample never lands the aircraft. GPS loss demands LAND rather than RTL because a home-bound trajectory is not navigable without positioning.
- **Severity ordering.** The demanded action is monotone non-decreasing within a mission: a LAND demand is never replaced by RTL. Escalation is honoured *mid-recovery*—the RTL phase re-reads the demand on every iteration and, if it has escalated (e.g., battery fell from low to critical during the return), abandons the return and commands LAND through the verified setter.
- **Fire-once event discipline.** Each named hazard emits one event per mission, with re-emission accepted only when it escalates the demanded action, keeping the incident record free of duplicate floods from persistent conditions.

The executor consults the arbiter inside every blocking loop and at every phase boundary, so no flight phase can outlive a demanded recovery by more than one polling interval.

### E. Geofence Validation at the Network Edge

The trigger interface validates every dispatch target and every in-flight waypoint against a software geofence centred on home, rejecting non-compliant requests with a client error *before any flight activity*—converting what would otherwise be an in-flight abort into a pre-flight validation error. The software fence is secondary to the autopilot's own hardware-level `FENCE_*` enforcement, which is also configured on real airframes.

### F. DELIVERING: The Payload Phase

For VanniKawachh missions the state machine inserts a DELIVERING phase between HOVERING and RTL. The drone descends over the incident point to the configured drop altitude (≤ 3 m), commands the SG90 release hook through the flight controller with `MAV_CMD_DO_SET_SERVO` on an AUX output channel, and climbs back to cruise altitude. Two rules are enforced: the kit is released only from a ≤ 3 m hover, and a *failed release is reported but never blocks the mission*—the drone proceeds to RTL either way, never loitering on a failed drop. The camera recorder runs across HOVERING and DELIVERING, writing an MP4 tagged with the mission ID as the evidence artifact; on machines without a camera (SITL, development hosts) it is a no-op stub so the mission flow is identical.

## VII. Experimental Results

All results in this section are software-in-the-loop or automated-test results, obtained with the ArduPilot SITL simulator [15] in place of a physical airframe. We state explicitly what each number is and is not; hardware measurements pending as of this writing are enumerated in Section VII-D.

### A. SITL Flight Validation

The acceptance harness spawns an ArduCopter SITL instance and the full flight stack as child processes, dispatches a mission over the real HTTP trigger interface, and monitors live telemetry throughout. Results:

- **8 of 8 acceptance checks passed**: API health and vehicle connection, mission acceptance, arming and takeoff, cruise-altitude attainment, target arrival within tolerance, hover phase, RTL, and landed/disarmed completion.
- **Terminal accuracy of 0.4 m** against the configured 5 m waypoint tolerance—the minimum distance-to-target observed during the approach.
- **Complete autonomous mission in 328 s** wall-clock, from trigger POST to landed-and-disarmed.
- **Battery drained from 100% to 32%** over the run with **zero false failsafe activations**: neither the low-battery nor any other failsafe fired spuriously during a nominal mission, while remaining armed at the 1 Hz polling cadence throughout.

### B. Unit Verification

A suite of **68 automated tests** pins the safety and security properties claimed in Sections IV–VI: failsafe thresholds, debounce behaviour (no trigger at N−1 anomalous GPS samples, trigger at N, count reset on recovery), severity escalation including LAND-over-RTL mid-return and refusal to downgrade LAND; queue landing interlocks; alert-packet seal/unseal round-trips, tamper rejection (corrupted MAC), and replay rejection (stale counter); fusion scoring; pipeline dispatch gating (no dispatch below threshold); and obstacle keep-out route geometry. Every safety claim written in this paper is pinned by at least one of these tests or by the acceptance harness.

### C. End-to-End Chain Rehearsal (Phase 0)

A full-chain rehearsal exercised every architectural interface with zero hardware: a simulated node event was sealed into the 25-byte packet format, delivered to the hub pipeline, authenticated and decrypted, verified and fused (fused severity 0.88, priority *high*), resolved against the node registry, and dispatched as an HTTP trigger; the SITL drone then flew the mission autonomously—takeoff, transit, hover-observe with the (no-op) evidence recorder, descent to 3.1 m for payload release, simulated servo release, return, and landing, with the state machine terminating in COMPLETED. This rehearsal validates the *integration contract* of the whole chain: packet format, registry lookup, gating thresholds, dispatch payload, and mission state sequence. Two caveats apply and are stated plainly: the rehearsal's Stage-2 scoring used the hub's energy-heuristic fallback backend rather than PANNs (which deploys on the physical Pi 5), and the simulated node used the calibrated heuristic Stage-1 screen rather than a trained TFLM model. The rehearsal is therefore evidence of architectural correctness, not of acoustic detection accuracy.

### D. Evaluation in Progress

The following measurements require physical hardware and are scheduled in the build plan; none are claimed in this paper.

**Table III. Pending hardware measurements (evaluation in progress)**

| Measurement | Phase | Status |
|---|---|---|
| Stage-1 TFLM model accuracy/recall on scream + keyword corpora | Phase 1 | Model training pending; heuristic stand-in deployed |
| Stage-1 on-device latency on ESP32-S3 (< 50 ms target) | Phase 1 | Not yet measured |
| Outdoor detection distance vs. SNR (INMP441, street noise) | Phase 1 | Not yet measured |
| Stage-2 PANNs latency on Raspberry Pi 5 | Phase 1 | Not yet measured |
| End-to-end false-positive rate on real street noise | Phase 1–2 | Not yet measured |
| LoRa range (urban / open) and packet loss vs. spreading factor | Phase 2 | Not yet measured |
| Physical flight replication of SITL results (VLOS field trials) | Phase 3–4 | Not yet flown |

Accordingly, this paper's validated contribution is best characterized as *architecture + safety framework + software-in-the-loop validation of the response chain*, with the acoustic pipeline's accuracy figures deferred to the hardware evaluation phases.

## VIII. Discussion

### A. Privacy by Construction

A pole-mounted microphone network invites legitimate privacy concern, and VanniKawachh addresses it structurally rather than by policy. There is no continuous recording and no continuous transmission: audio is processed in place on the node and discarded frame-by-frame unless Stage 1 fires. Only event-triggered clips of at most 5 s ever leave a node, and the alert itself is encrypted. The node stores no audio at rest, and the hub retains clips only as incident evidence. Because nodes carry no GPS and no identity beyond a numeric ID, a captured node reveals its own derived key but neither the master key nor any location data beyond what is physically observable.

### B. Regulatory Context

Prototype flight operations comply with India's Drone Rules 2021: the airframe is registered, all test flights are conducted within visual line of sight (VLOS) over open private ground with an RC safety pilot holding override authority at all times. Fully autonomous beyond-visual-line-of-sight (BVLOS) response—the operationally interesting deployment mode—is described here as a *supervised pilot-program pathway* contingent on regulatory approval, not as a capability of the prototype. The architecture anticipates this: the police dashboard already provides the human-supervision surface (live telemetry, incident log, and a recall endpoint that is the operator's only override—there is deliberately no joystick).

### C. Limitations

Beyond the pending measurements of Table III, several limitations are acknowledged. (1) The fusion weights and dispatch thresholds are prototype values pending calibration against bench data; the false-alarm behaviour of the full two-stage pipeline in real acoustic environments is the single most important unvalidated property. (2) The 25-byte alert's 8-byte truncated MAC trades authentication strength for frame budget; at LoRa alert rates, brute-force forgery is impractical, but the trade-off should be revisited if the channel is ever widened. (3) The hub is a single point of failure per locality; node-to-node relaying and hub redundancy are not yet designed. (4) The clip path (ESP-NOW/WiFi) has far shorter range than the alert path, so nodes far from the hub will operate predominantly in the degraded-score mode. (5) SITL validates control logic, not aerodynamics, wind, GPS multipath, or real sensor noise; physical flight trials may surface effects the simulator does not model. (6) One drone serves one locality serially; concurrent incidents queue by priority rather than being served in parallel.

## IX. Conclusion and Future Work

VanniKawachh demonstrates that a women-safety system need not place any burden—device, charge, coverage, or action—on the woman it protects. The architecture couples infrastructure-mounted two-stage acoustic sensing to an offline, cryptographically sealed alert channel and an autonomous aerial first-response layer whose safety rests on verified command delivery, severity-ordered failsafe arbitration, and a landing-interlocked dispatch queue. Software-in-the-loop validation shows the complete chain—from sealed alert to first-aid drop—functioning end-to-end with 8/8 acceptance checks and 0.4 m terminal accuracy, and 68 automated tests pin every stated safety property.

Future work proceeds on two fronts. Near-term hardware evaluation (Table III) will supply the acoustic accuracy, latency, range, and false-alarm figures this paper deliberately declines to estimate. Beyond that, four extensions are planned: live video streaming from the drone to the police dashboard (RTSP/WebRTC); OpenCV-based victim detection and tracking during hover; multi-node time-difference-of-arrival (TDOA) localization to position events between poles rather than at them; and a city-scale node mesh with hub federation. The flight-safety mechanisms of Section VI are the subject of two Indian patent applications in preparation.

## Acknowledgment

The authors thank Dr. Aditya Turankar, Department of Computer Science and Engineering, G H Raisoni College of Engineering, Nagpur, for guidance throughout this work.

## References

[1] R. Pavithra, R. Ahalya, and C. Shuruthika, "Discreet AI-powered women's safety app with audio recognition and emergency automation," in *Proc. 2026 IEEE Students Conf. Eng. Syst. (SCEECS)*, Bhopal, India, 2026, doi: 10.1109/SCEECS68810.2026.11430037.

[2] Y. Kim, D. Jang, and S.-P. Lee, "Robust scream detection and scream temporal interval prediction using CNN-Transformer and windowing CNN," *IEEE Access*, vol. 13, pp. 71374–71387, 2025, doi: 10.1109/ACCESS.2025.3556729.

[3] P. Sharma and T. J. Jebaseeli, "Smart scream and panic detection system for women using AI," in *Proc. 2025 Int. Conf. Autom. Comput. Renew. Syst. (ICACRS)*, 2025, pp. 1554–1559, doi: 10.1109/ICACRS67045.2025.11324333.

[4] A. Srimathi, S. Jothi, and M. P. Sindhiya, "Human scream detection and analysis for crime reduction," in *Proc. 2025 Int. Conf. Multidiscip. Sci. Comput. Intell. (ICMSCI)*, Erode, India, 2025, pp. 1528–1534, doi: 10.1109/ICMSCI62561.2025.10894058.

[5] P. S. Bharathi et al., "A novel IoT enabled women safety system design with emergency alert mechanism," in *Proc. 2025 Int. Conf. Future Technol. Syst. (ICFTS)*, 2025, pp. 1–7, doi: 10.1109/ICFTS62006.2025.11031774.

[6] R. Snehith, S. Saranya, and N. R. Reddy, "A smart device for women safety using IoT," in *Proc. 2025 Int. Conf. Intell. Syst. Sci. (ICISS)*, 2025, pp. 277–282, doi: 10.1109/ICISS63372.2025.11076270.

[7] Y. Kim, D. Jang, and J. Lee, "Development of scream detection system with large-scale scream dataset," in *Proc. 2024 Int. Conf. Inf. Commun. Technol. Converg. (ICTC)*, Jeju, South Korea, 2024, pp. 590–593, doi: 10.1109/ICTC62082.2024.10826757.

[8] A. A. Fime, M. Ashikuzzaman, and A. Aziz, "Audio signal-based danger detection using signal processing and deep learning," *Expert Systems with Applications*, vol. 237, art. no. 121646, Mar. 2024, doi: 10.1016/j.eswa.2023.121646.

[9] R. V. Hadkar et al., "An efficient IoT-enabled women safety device," in *Proc. 2024 Int. Conf. Autom. Comput. Renew. Syst. (ICACRS)*, 2024, pp. 425–431, doi: 10.1109/ICACRS62842.2024.10841797.

[10] G. Uganya et al., "Smart women safety device using IoT and GPS tracker," in *Proc. 2023 Int. Conf. Comput. Electron. Biomed. Syst. (ICCEBS)*, Chennai, India, 2023, pp. 1–6, doi: 10.1109/ICCEBS58601.2023.10449302.

[11] S. Potturi et al., "An SOS women safety device: Automatic emergency alerts and geo-location sharing with GSM/GPS integration," in *Proc. 2026 Int. Conf. Intell. Comput. Netw. Syst. (IC-ICNS)*, Bhubaneswar, India, 2026, pp. 1–6, doi: 10.1109/IC-ICNS68863.2026.11537940.

[12] G. Ciaburro and V. Puyana-Romero, "Sound event detection in smart cities: A systematic review of methods, datasets, and applications," *Big Data and Cognitive Computing*, vol. 10, no. 3, art. no. 83, 2026, doi: 10.3390/bdcc10030083.

[13] Q. Kong, Y. Cao, T. Iqbal, Y. Wang, W. Wang, and M. D. Plumbley, "PANNs: Large-scale pretrained audio neural networks for audio pattern recognition," *IEEE/ACM Trans. Audio, Speech, Lang. Process.*, vol. 28, pp. 2880–2894, 2020, doi: 10.1109/TASLP.2020.3030497.

[14] R. David et al., "TensorFlow Lite Micro: Embedded machine learning for TinyML systems," in *Proc. Mach. Learn. Syst. (MLSys)*, vol. 3, 2021, pp. 800–811.

[15] ArduPilot Development Team, "ArduPilot documentation" and MAVLink Development Team, "MAVLink developer guide." [Online]. Available: https://ardupilot.org/ and https://mavlink.io/. Accessed: Jul. 2026.

[16] LoRa Alliance, "LoRaWAN L2 1.0.4 specification," LoRa Alliance Technical Committee, 2020. [Online]. Available: https://lora-alliance.org/resource_hub/lorawan-104-specification-package/.

[17] National Institute of Standards and Technology, "Advanced Encryption Standard (AES)," FIPS PUB 197, Nov. 2001, doi: 10.6028/NIST.FIPS.197.
