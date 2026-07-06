<!--
NOTE: docs/JOURNAL_PAPER.md is the extended journal version of this
paper, being prepared in parallel. Keep the two consistent in claims:
all measured numbers (68/68 unit cases, 8/8 SITL acceptance, 0.4-0.6 m
terminal accuracy, Phase-0 rehearsal with fused severity 0.88 and kit
release at 3.1 m, 328 s mission) are shared; neither document may claim
acoustic accuracy figures or hardware radio/range measurements, which
are Phase 1-2 work in progress.
-->

# VanniKawachh: A Distributed AI Acoustic Intelligence and Autonomous Drone Response Network for Women Safety

**Shivansh Verma, Saksham Sabadra, Rudra Thakur, Rohan Untawale**
Group CSE_B_04, Department of Computer Science and Engineering
G. H. Raisoni College of Engineering, Nagpur — Session 2026–27
**Guide:** Dr. Aditya Turankar
**Repository:** <https://github.com/SV-1411/drone.git>
**Status:** Conference pre-print (v2 concept — supersedes the v1
flight-stack paper of 2026-06-11)

---

## Abstract

Crimes against women concentrate in surveillance and cellular dead
zones — dark streets, forest stretches, campus outskirts — and the
prevailing safety technology burdens the victim: panic apps, wearables,
and carried devices protect only the moments in which a charged,
reachable device is in the victim's hand. We present **VanniKawachh**,
a three-tier network that moves the trigger burden from the victim to
the infrastructure: her voice is the trigger. Solar-powered,
pole-mounted sensing nodes (ESP32-S3 + INMP441) screen every audio
frame on-device with a lightweight MFCC + CNN model (Stage 1, < 50 ms
budget, recall-tuned), so no continuous audio ever leaves a pole. A
Raspberry Pi 5 hub confirms candidate events with PANNs deep audio
tagging fused with PIR motion, ambient-light, and time-of-day evidence
(Stage 2, precision-tuned), gating dispatch behind explicit
verification and severity thresholds. Confirmed alerts — 25-byte
packets sealed with AES-128-CTR, truncated HMAC-SHA256, and a per-node
replay counter, carrying surveyed node coordinates from a registry
rather than a live GPS fix — travel over LoRa with no cellular
dependency to a police dashboard, and simultaneously auto-dispatch an
autonomous quadcopter that records evidence during hover, descends to
3 m, drops a first-aid kit (fail → return-to-launch), and returns. The
response layer is our previously SITL-verified flight stack — verified
mode transition, a landing-interlocked mission queue, and a debounced
severity-ordered failsafe arbiter — carried over unchanged. The
complete chain runs end-to-end with zero hardware: the Phase-0
rehearsal passed with fused severity 0.88 and kit release commanded at
3.1 m inside a 328 s SITL mission; the acceptance harness passes 8/8
checks with 0.4–0.6 m terminal accuracy; 68 automated unit cases pin
the safety logic, packet cryptography, and dispatch gating. Stage-1
model training and hardware range measurements are Phase 1–2 work in
progress; the development chain used clearly labelled heuristic
stand-ins, and this paper reports no acoustic accuracy it has not
measured.

**Keywords:** women safety; acoustic event detection; TinyML; PANNs;
sensor fusion; LoRa; AES-128; autonomous UAV; verified dispatch; SITL.

---

## 1. Introduction

Where does safety technology fail? Precisely where assaults happen: in
locations that are camera-poor, patrol-poor, and often cellular dead
zones, at moments when the victim cannot operate a device — hands
occupied, phone snatched, discharged, or out of reach. The deployed
answer to women's safety has been to instrument the victim: panic
buttons, mobile apps, smart wearables. The best of these report high
trigger accuracy, but their failure mode is structural rather than
statistical — a device-borne trigger protects only the moments in
which the device is present, charged, and reachable.

VanniKawachh ("voice-shield") inverts the burden. Pole-mounted
infrastructure listens; a scream, a cry, or a shouted "help" /
"bachao" — signals the victim produces with no device at all — is the
trigger. The engineering problem is then threefold: (i) detection must
run on a solar pole budget without streaming audio anywhere;
(ii) false alarms must be suppressed well enough that acting on an
alert is defensible, because the action is a drone launch; (iii) the
alert path must work exactly where cellular does not, and must be
unforgeable, because a spoofed alert weaponizes the response.

Our contributions:

1. An **end-to-end architecture** — infrastructure sensing → two-stage
   verification → offline encrypted alerting → autonomous field
   response — where surveyed prior work covers at most one link (§2).
2. A **two-stage acoustic pipeline** splitting recall and precision
   between an on-node TinyML screen and a hub-side PANNs +
   sensor-fusion confirmation, with tested dispatch gating (§4).
3. A **secure LoRa alert protocol**: sealed 25-byte packets resolved
   against a surveyed node registry, so position is never transmitted
   or trusted from the field (§5).
4. A **safety-verified autonomous response layer** — our SITL-verified
   dispatch stack, extended with an evidence camera window and a
   rule-bounded first-aid kit drop (§6).
5. A **zero-hardware full-chain validation** (Phase 0) demonstrating
   the integrated system in software-in-the-loop simulation, with an
   explicit account of which numbers are measured and which await the
   hardware phases (§7).

## 2. Related Work

Our twelve-paper survey (2023–2026; entries [S1]–[S12], full
bibliography in the group's seminar record and the journal version)
partitions the field on one question: who carries the trigger?

**Victim-carried devices** ([S1], [S5], [S6], [S9], [S10], [S11]) —
apps, wearables, IoT panic buttons — report trigger-classification
accuracies up to **97.5%**, typically with GPS + GSM alerting. All
fail identically when the device is absent, damaged, discharged, or
unreachable, and inherit cellular dependence in exactly the locations
that lack it.

**Detection-only audio systems** ([S2], [S3], [S4], [S7], [S8]) reach
**92–95.5%** scream detection with CNN–Transformer hybrids and
transfer-learned backbones (InceptionV3, MobileNetV2) on
mel-spectrograms — but on server-scale compute, evaluated on curated
data, and stopping at classification: no location delivery, no
dead-zone alerting, no response.

**The gap** is the chain itself: no surveyed system provides
infrastructure sensing → verified offline alerting → autonomous
response end to end. Each link is individually supported by adjacent
literatures — TensorFlow Lite Micro keyword spotting [7] for the node,
PANNs large-scale pretrained audio tagging [6] for the hub, LPWAN
practice [8] for the alert path, and the open-source autopilot
ecosystem [1][2] for the response — and our prior flight-stack work
supplies the response layer's safety machinery, including the
empirical finding that motivates the whole design philosophy: flight
autopilots can *silently reject* mode commands while client libraries
report success. VanniKawachh generalizes the resulting discipline —
*a claim is not a confirmation* — to every layer: sound, packet,
dispatch, and flight mode.

## 3. System Architecture

```
 SENSING NODE (per pole, solar)          HUB (Raspberry Pi 5, per locality)
┌─────────────────────────────┐         ┌────────────────────────────────┐
│ INMP441 I2S mic 16 kHz      │  LoRa   │ gateway ESP32+SX1278 (USB)     │
│ ESP32-S3: MFCC + tiny CNN   │ ──────▶ │ unseal: AES-128 + MAC + replay │
│ (TFLM, <50 ms, recall-tuned)│ sealed  │ registry: node_id→(lat,lon)    │
│ PIR + LDR context           │ alert   │ Stage 2: PANNs + fusion score  │
│ Stage-1 hit → alert + clip  │         │ police dashboard + alert log   │
└──────────────┬──────────────┘         └───────────────┬────────────────┘
               └── WiFi/ESP-NOW: 4 s clip ──▶            │ POST /trigger
                                                         ▼
                                  RESPONSE DRONE (SITL-verified stack)
                                 ┌────────────────────────────────────┐
                                 │ trigger API → queue → 13-state FSM │
                                 │ verified mode setter · failsafe    │
                                 │ arbiter · landing interlock        │
                                 │ HOVER+record → DELIVER (3 m kit    │
                                 │ drop, fail→RTL) → RTL              │
                                 └────────────────────────────────────┘
```

*Figure 1 — The VanniKawachh chain. Each tier verifies before it acts.*

Three design decisions carry the architecture. **Fixed nodes carry no
live GPS:** each pole is surveyed once at installation; the hub's
registry maps `node_id → (lat, lon)`, so the radio carries two bytes
of identity, and a node has no GPS to spoof, jam, or drain. **LoRa
carries the alert, never the audio:** LoRa's ~1–5.5 kbps effective
throughput cannot move a clip, so the sealed alert goes over LoRa
instantly while the 4 s verification clip follows over ESP-NOW/WiFi
(~250 kbps, hundreds of metres LOS); if the clip never arrives within
8 s, the hub degrades to the Stage-1 confidence at a ×0.6 haircut —
always logging, dispatching only on otherwise-strong evidence. **The
flight core is untouched:** all v1 safety machinery carries over
unchanged, which is why the response half of the system already works.

## 4. The Two-Stage Acoustic Pipeline

**Stage 1 (node, recall-tuned).** The ESP32-S3 frames 16 kHz mono
audio from the INMP441, extracts MFCCs, and runs a tiny quantized CNN
(TensorFlow Lite Micro, `micro_speech`-class [7]) against the distress
vocabulary — scream, cry, "help"/"bachao" keywords — within a < 50 ms
per-frame budget. Frames that do not trip Stage 1 are discarded on
the spot: nothing stored, nothing transmitted. Stage 1 exists to *not
miss*; its false positives are expected and cheap because Stage 2
filters them. (The model itself is a hook in the current firmware;
training and flashing it is Phase-1 work — §7.3.)

**Stage 2 (hub, precision-tuned).** The hub re-scores the clip with
PANNs [6] — the pretrained AudioSet tagging network (CNN14, or a
lighter checkpoint on a slow Pi) — taking the summed probability over
the distress-relevant AudioSet classes (screaming, shouting, yelling,
crying, wailing, …) as a distress score in [0, 1]. No bespoke training
is required; the hub leans on AudioSet scale, which a locality Pi 5
can afford and a solar pole cannot. A labelled energy-heuristic
fallback backend (loud + high-spectral-centroid + bursty) exists so
the whole chain runs on any development machine; it is not a claim of
accuracy and every result produced with it is marked as fallback.

**Fusion.** A night-time scream in a dark spot with motion nearby is
a different animal from a daytime shout on a busy road. The fused
severity is

```
severity = 0.60·audio + 0.15·stage1_conf + 0.10·PIR
         + 0.08·darkness + 0.07·night
```

with priority `high` at severity ≥ 0.75 or verified audio (≥ 0.6)
coinciding with PIR motion. Dispatch requires **both** audio score
≥ 0.50 and severity ≥ 0.60; below either threshold the incident is
logged with a human-readable reasons trace and no drone flies. The
gating is pinned by automated tests, and the weights are prototype
values to be tuned against Phase-1 bench data.

## 5. Secure LoRa Alerting

A spoofed packet would launch a drone; a replayed one would launch it
at an attacker's chosen time. Every alert is therefore a sealed
25-byte packet — one comfortable LoRa frame: a cleartext header
(magic, version, node_id uint16, counter uint32), an 8-byte
AES-128-CTR-encrypted payload (event class, Stage-1 confidence, PIR
flag, LDR level, node battery), and an 8-byte MAC (HMAC-SHA256 over
header + ciphertext, truncated). The CTR nonce derives from the
header, unique per packet while the counter is monotonic; the hub
rejects bad MACs, unknown node ids, and any counter not exceeding the
node's last accepted value. Per-node keys derive as
HMAC-SHA256(master_key, "node:<id>")[:16], so provisioning needs only
the master key and an id, and a captured node compromises one pole,
revocable in the registry. Above the radio, the hub reaches the drone
stack through the same token-authenticated, geofence-validated API as
any operator — no privileged backdoor. Residual risk is stated:
jamming is a denial, not a spoof; multi-node corroboration and
node-liveness monitoring are future answers.

Privacy is by construction, not policy: continuous audio cannot leave
a node because the transport cannot carry it and the clip path is
event-gated in firmware; only event-triggered clips ≤ 5 s are ever
transmitted, and the alert itself is encrypted.

## 6. Safety-Verified Drone Response

The response layer is our SITL-verified dispatch stack, whose three
mechanisms transfer intact. **Verified mode transition:** every
flight-mode command — nominal or emergency — routes through a single
routine that re-issues the request through layered MAVLink encodings
(`COMMAND_LONG`/`MAV_CMD_DO_SET_MODE` plus legacy `SET_MODE`) on a
700 ms cadence until the autopilot's own HEARTBEAT-derived mode
confirms adoption, with a cross-action fallback (RTL ⇄ LAND) on the
abort path — the design answer to observed silent rejection on
ArduCopter 3.3 SITL. **Landing interlock:** every abnormal termination
blocks until the vehicle demonstrably lands and disarms (bounded
240 s) before the queue regains control, and a dequeued mission
refuses to arm an armed vehicle — jointly, the queue can never start a
flight against an airborne vehicle. **Failsafe arbitration:** battery,
GPS, geofence, and timeout monitors feed a 1 Hz arbiter with monotone
severity (LAND never downgraded), N-sample GPS debounce, fire-once
event semantics, and mid-RTL escalation.

v2 adds the response payload. The mission FSM (now thirteen states)
records camera evidence during the hover window (Pi Camera Module 3
on hardware; a no-op stub in SITL, so the flow is byte-identical) and
then enters **DELIVERING**: descend over the incident point to the
configured drop altitude (3.0 m, tolerance 0.7 m, bounded at 45 s),
release the first-aid kit via an SG90 servo on Pixhawk AUX OUT 1
commanded with `MAV_CMD_DO_SET_SERVO` (open 1900 PWM, 2 s settle,
re-close 1100), then climb back to cruise altitude for a clean RTL.
The governing rule: **a failed release is never a reason to loiter** —
the failure is logged and the drone proceeds to RTL regardless; and
the DELIVERING loop polls the failsafe arbiter like every other
phase, so a battery or GPS demand pre-empts the drop. All prototype
flying is VLOS-only on a registered airframe with an RC safety pilot,
per India's Drone Rules 2021 [5]; autonomous BVLOS response is
described strictly as a supervised pilot-program pathway.

## 7. Evaluation

### 7.1 Methodology

Validation is staged. **Tier 1:** 68 automated unit cases — 47 over
the flight stack's safety logic (every arbiter rule, queue semantics,
persistence, every edge-validation bound), 14 over the hub chain
(packet seal/unseal, MAC tamper rejection, replay rejection, registry,
fusion, pipeline gating — *no dispatch below threshold* is asserted,
not assumed — and dispatcher payload shape), 7 over obstacle keep-out
routing. The suites discriminate: run against the pre-hardening
implementation, the debounce, cancel, and interlock cases fail.
**Tier 2:** an eight-property SITL acceptance flight (ArduCopter 3.3;
896 m mission at 15 m altitude): simulator up, API up, connected,
armed, took off, reached target (≤ 5 m), returned home (≤ 10 m,
required), landed. **Tier 3:** the Phase-0 full-chain rehearsal
(`scripts/demo_phase0.py`) — a synthesized distress WAV stands in for
the microphone, a simulated node 600 m from home seals a real packet
with the production cryptography, the production hub pipeline
verifies (fallback backend), fuses, gates, and dispatches, and the
production drone stack flies the SITL mission with hover-record and
kit drop. Everything except the audio source, the Stage-2 backend,
and the physics is production code.

### 7.2 Results

Tier 1: **68/68 pass.** Tier 2: **8/8 checks pass**; across six
acceptance missions spanning the development arc, closest approach was
0.4–0.6 m against the 5 m tolerance and final distance from home
0.0–0.2 m — terminal accuracy bounded by the autopilot's loiter
behaviour, not the dispatch layer. Tier 3: the rehearsal **passed end
to end** — the sealed alert (event `scream`, PIR active, dark LDR)
authenticated and replay-checked; the fallback backend scored the
clip above the 0.50 verification threshold; **fused severity 0.88**
(priority `high`) cleared the 0.60 dispatch gate; the SITL mission
ran the full lifecycle with the recording window active and **kit
release commanded at 3.1 m** relative altitude, completing in
**328 s** with 0.4 m closest approach.

### 7.3 What is measured vs. in progress

The Phase-0 result proves architecture and integration: every
interface a hardware phase will use — packet bytes, clip convention,
thresholds, trigger payload, servo command — was exercised in
production form. It deliberately proves nothing about acoustic
detection performance. **No Stage-1 accuracy exists** (the TFLM model
is a hook; training and flashing it is Phase 1; < 50 ms is a design
budget, not a measurement). **No field Stage-2 accuracy exists** (the
Phase-0 score came from the labelled heuristic fallback on synthesized
audio; PANNs' published performance [6] motivates the backend, not a
field claim). **No radio range/loss or ESP-NOW reliability figures
exist** (Phase 2). **No hardware flight has occurred** (Phase 3's
staged VLOS progression governs the transition; the SITL firmware is
the 2015-vintage 3.3 build, whose command-delivery faults usefully
forced the defensive design). These measurements — outdoor detection
distance vs. SNR, per-stage latency, end-to-end false-positive rate on
street noise, LoRa range vs. spreading factor — are the explicit
deliverables of the Phase 1–2 bench campaigns and will appear in the
journal version once measured.

## 8. Conclusion

VanniKawachh integrates TinyML pole-side screening, pretrained deep
audio verification with environmental fusion, sealed operator-free
alerting, and a safety-interlocked autonomous first response into a
single women-safety chain that asks nothing of the victim but her
voice — and demonstrates the complete chain in simulation before any
hardware is committed. One discipline governs every layer: a claim is
not a confirmation. A Stage-1 hit is not an incident until Stage 2 and
fusion say so; a packet is not an alert until its MAC and counter say
so; a mode command is not a mode until the autopilot's telemetry says
so; a mission is not finished until the vehicle is disarmed on the
ground. Under that discipline the integrated rehearsal passed on the
first architecture, and the remaining work is measurement and
hardening rather than redesign. Future work: the Phase 1–2 measurement
campaigns; live RTSP/WebRTC streaming to police; OpenCV victim
tracking during hover; TDOA multi-node localization between poles; and
the city-scale node mesh with fleet dispatch.

---

## References

- **[1] ArduPilot Project.** Firmware, SITL, and failsafe
  documentation. <https://ardupilot.org>. Accessed 2026-07-06.
- **[2] MAVLink Developer Guide.** Protocol specification (HEARTBEAT,
  SET_MODE, COMMAND_LONG/`MAV_CMD_DO_SET_MODE`,
  `MAV_CMD_DO_SET_SERVO`). <https://mavlink.io/en/>. Accessed
  2026-07-06.
- **[3] dronekit-sitl 3.3.0.**
  <https://github.com/dronekit/dronekit-sitl>. Accessed 2026-07-06.
- **[4] Pixhawk hardware reference.** <https://pixhawk.org>. Accessed
  2026-07-06.
- **[5] Ministry of Civil Aviation, Government of India.** The Drone
  Rules, 2021; DigitalSky platform.
  <https://digitalsky.dgca.gov.in>. Accessed 2026-07-06.
- **[6] Q. Kong, Y. Cao, T. Iqbal, Y. Wang, W. Wang, M. D. Plumbley.**
  "PANNs: Large-Scale Pretrained Audio Neural Networks for Audio
  Pattern Recognition," IEEE/ACM Trans. Audio, Speech, and Language
  Processing, vol. 28, 2020; `panns-inference` package.
- **[7] TensorFlow Lite for Microcontrollers.** Documentation and the
  `micro_speech` example.
  <https://www.tensorflow.org/lite/microcontrollers>. Accessed
  2026-07-06.
- **[8] Semtech SX1276/77/78/79.** LoRa transceiver datasheet.
  <https://www.semtech.com>. Accessed 2026-07-06.
- **[9] InvenSense/TDK INMP441.** Omnidirectional I2S MEMS microphone
  datasheet. <https://invensense.tdk.com>. Accessed 2026-07-06.
- **[10] NIST FIPS-197** (AES); **RFC 2104** (HMAC).
- **[S1]–[S12]** Literature-survey entries (twelve papers, 2023–2026)
  on victim-carried safety devices and acoustic distress detection;
  full bibliographic details in the group's Title Finalization Seminar
  record, reproduced in the journal version (`docs/JOURNAL_PAPER.md`).

---

## Reproducibility and originality statement

The full chain is reproducible on any machine with no hardware and no
paid service: `git clone https://github.com/SV-1411/drone.git`, a
Python 3.10+ environment, `pip install -r requirements-dev.txt` plus
`requirements-hub.txt`, then `python -m pytest` (tier 1),
`python tests/test_full_mission.py` (tier 2, boots SITL locally), and
`python scripts/demo_phase0.py` (tier 3, the full-chain rehearsal).
All prose was written for this work; protocol, parameter, and
flight-mode names are protocol- or firmware-defined identifiers. A
large-language-model assistant was used during drafting for structure
and consistency; all technical claims derive from the implementation
and test logs in the repository, and the final text was reviewed and
accepted by the authors.
