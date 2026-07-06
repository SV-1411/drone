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
G. H. Raisoni College of Engineering, Nagpur, Session 2026-27
**Guide:** Dr. Aditya Turankar
**Repository:** <https://github.com/SV-1411/drone.git>
**Status:** Conference pre-print (v2 concept; supersedes the v1
flight-stack paper of 2026-06-11)

---

## Abstract

Crimes against women often happen in surveillance and cellular dead
zones such as dark streets, forest stretches, and campus outskirts.
Most safety technology puts the burden on the victim: panic apps,
wearables, and carried devices only work while a charged, reachable
device is in the victim's hand. We present **VanniKawachh**, a
three-tier network that moves the trigger burden from the victim to
the infrastructure. Her voice is the trigger. Solar-powered,
pole-mounted sensing nodes (ESP32-S3 + INMP441) screen every audio
frame on-device with a lightweight MFCC + CNN model (Stage 1, < 50 ms
budget, recall-tuned), so no continuous audio ever leaves a pole. A
Raspberry Pi 5 hub confirms candidate events with PANNs deep audio
tagging fused with PIR motion, ambient-light, and time-of-day evidence
(Stage 2, precision-tuned), and dispatches only above explicit
verification and severity thresholds. A confirmed alert is a 25-byte
packet sealed with AES-128-CTR, a truncated HMAC-SHA256 tag, and a
per-node replay counter. It carries surveyed node coordinates from a
registry rather than a live GPS fix, and travels over LoRa with no
cellular dependency to a police dashboard. The same alert
auto-dispatches an autonomous quadcopter that records evidence during
hover, descends to 3 m, drops a first-aid kit (on failure it returns
to launch), and returns. The response layer is our previously
SITL-verified flight stack (verified mode transition, a
landing-interlocked mission queue, and a debounced severity-ordered
failsafe arbiter), carried over unchanged. The complete chain runs
end-to-end with zero hardware: the Phase-0 rehearsal passed with fused
severity 0.88 and kit release commanded at 3.1 m inside a 328 s SITL
mission; the acceptance harness passes 8/8 checks with 0.4 to 0.6 m
terminal accuracy; 68 automated unit cases cover the safety logic,
packet cryptography, and dispatch gating. Stage-1 model training and
hardware range measurements are Phase 1 and 2 work in progress. The
development chain used clearly labelled heuristic stand-ins, and this
paper reports no acoustic accuracy it has not measured.

**Keywords:** women safety; acoustic event detection; TinyML; PANNs;
sensor fusion; LoRa; AES-128; autonomous UAV; verified dispatch; SITL.

---

## 1. Introduction

Safety technology fails where assaults happen: in places with few
cameras, few patrols, and often no cellular coverage, at moments when
the victim cannot operate a device because her hands are occupied or
the phone is snatched, discharged, or out of reach. The deployed
answer to women's safety has been to instrument the victim with panic
buttons, mobile apps, and smart wearables. The best of these report
high trigger accuracy, but their failure mode is structural: a
device-borne trigger protects only the moments in which the device is
present, charged, and reachable.

VanniKawachh ("voice-shield") moves the burden. Pole-mounted
infrastructure listens. A scream, a cry, or a shouted "help" /
"bachao" is the trigger, and the victim needs no device to produce it.
The engineering problem then has three parts: (i) detection must
run on a solar pole budget without streaming audio anywhere;
(ii) false alarms must be suppressed well enough that acting on an
alert is defensible, because the action is a drone launch;
(iii) the alert path must work exactly where cellular does not, and it
must be unforgeable, because a spoofed alert would launch the drone
for an attacker.

Our contributions:

1. An **end-to-end architecture** covering infrastructure sensing,
   two-stage verification, offline encrypted alerting, and autonomous
   field response, where surveyed prior work covers at most one link
   (§2).
2. A **two-stage acoustic pipeline** that splits recall and precision
   between an on-node TinyML screen and a hub-side PANNs +
   sensor-fusion confirmation, with tested dispatch gating (§4).
3. A **secure LoRa alert protocol**: sealed 25-byte packets resolved
   against a surveyed node registry, so position is never transmitted
   or trusted from the field (§5).
4. A **safety-verified autonomous response layer**: our SITL-verified
   dispatch stack, extended with an evidence camera window and a
   rule-bounded first-aid kit drop (§6).
5. A **zero-hardware full-chain validation** (Phase 0) that runs the
   integrated system in software-in-the-loop simulation and states
   which numbers are measured and which await the hardware phases
   (§7).

## 2. Related Work

Our twelve-paper survey (2023 to 2026; entries [S1] to [S12], full
bibliography in the group's seminar record and the journal version)
splits the field on one question: who carries the trigger?

**Victim-carried devices** ([S1], [S5], [S6], [S9], [S10], [S11])
include apps, wearables, and IoT panic buttons. They report
trigger-classification accuracies up to **97.5%**, typically with
GPS + GSM alerting. All of them fail the same way when the device is
absent, damaged, discharged, or unreachable, and they depend on
cellular coverage in exactly the locations that lack it.

**Detection-only audio systems** ([S2], [S3], [S4], [S7], [S8]) reach
**92 to 95.5%** scream detection with CNN-Transformer hybrids and
transfer-learned backbones (InceptionV3, MobileNetV2) on
mel-spectrograms. But they run on server-scale compute, are evaluated
on curated data, and stop at classification: no location delivery, no
dead-zone alerting, no response.

**The gap** is the chain itself. No surveyed system provides
infrastructure sensing, verified offline alerting, and autonomous
response end to end. Each link is supported by adjacent work:
TensorFlow Lite Micro keyword spotting [7] for the node, PANNs
large-scale pretrained audio tagging [6] for the hub, LPWAN practice
[8] for the alert path, and the open-source autopilot ecosystem
[1][2] for the response. Our prior flight-stack work supplies the
response layer's safety machinery, including the finding that shaped
the design philosophy: flight autopilots can *silently reject* mode
commands while client libraries report success. VanniKawachh applies
the resulting rule, *a claim is not a confirmation*, to every layer:
sound, packet, dispatch, and flight mode.

## 3. System Architecture

![Figure 1: VanniKawachh decision methodology from acoustic event to autonomous response](figures/v2/fig2_methodology.png)

*Figure 1. The VanniKawachh chain, from acoustic event through Stage-1
on-node screening, Stage-2 hub verification and fusion, and sealed
LoRa alerting to the parallel dashboard and drone-dispatch paths. Each
tier verifies before it acts.*

Figure 1 traces one incident through the three tiers: the
solar-powered sensing node (ESP32-S3 + INMP441, PIR + LDR context,
Stage-1 hit → sealed alert over LoRa + 4 s clip over ESP-NOW/WiFi),
the Raspberry Pi 5 hub (unseal, registry lookup, Stage-2 PANNs +
fusion, police dashboard, `POST /trigger`), and the SITL-verified
response drone (trigger API → queue → 13-state FSM with hover-record,
3 m kit drop, and RTL).

Three design decisions shape the architecture. **Fixed nodes carry no
live GPS.** Each pole is surveyed once at installation. The hub's
registry maps `node_id → (lat, lon)`, so the radio carries two bytes
of identity, and a node has no GPS to spoof, jam, or drain. **LoRa
carries the alert, never the audio.** LoRa's effective throughput of
about 1 to 5.5 kbps cannot move a clip, so the sealed alert goes over
LoRa at once while the 4 s verification clip follows over ESP-NOW/WiFi
(about 250 kbps, hundreds of metres line of sight). If the clip does
not arrive within 8 s, the hub falls back to the Stage-1 confidence
scaled by 0.6; it always logs the incident, and dispatches only if the
remaining evidence is strong. **The flight core is untouched.** All v1
safety machinery carries over unchanged, which is why the response
half of the system already works.

## 4. The Two-Stage Acoustic Pipeline

**Stage 1 (node, recall-tuned).** The ESP32-S3 frames 16 kHz mono
audio from the INMP441, extracts MFCCs, and runs a tiny quantized CNN
(TensorFlow Lite Micro, `micro_speech`-class [7]) against the distress
vocabulary (scream, cry, and the "help"/"bachao" keywords) within a
< 50 ms per-frame budget. The front end is the standard speech chain:
each frame is pre-emphasised,

> y[n] = x[n] − 0.97·x[n−1], (1)

Hamming-windowed,

> w[n] = 0.54 − 0.46·cos(2πn/(N−1)), (2)

and its magnitude spectrum pooled by M triangular filters spaced
uniformly on the mel scale

> m = 2595·log₁₀(1 + f/700), (3)

giving log filterbank energies

> e_j = log Σ_k |X(k)|²·H_j(k), (4)

which a DCT-II decorrelates into the 13 cepstral coefficients used as
the per-frame feature vector,

> c_i = Σ_{j=1}^{M} e_j·cos[ i·(j − ½)·π/M ], i = 1, …, 13. (5)

The CNN classifies each MFCC frame through a softmax output,

> p_i = exp(z_i) / Σ_j exp(z_j), (6)

is trained with the cross-entropy loss

> L = −Σ_i y_i·log p_i, (7)

and deploys after int8 post-training quantization,

> x_q = round(x/s) + z, (8)

with per-tensor scale s and zero-point z. This quantization step fits
the model into TFLM on the ESP32-S3. Frames that do not trip Stage 1
are discarded on the spot: nothing is stored and nothing is
transmitted. Stage 1 exists to avoid misses; its false positives are
expected and cheap because Stage 2 filters them. (The model itself is
a hook in the current firmware; training and flashing it is Phase-1
work, see §7.3.)

**Stage 2 (hub, precision-tuned).** The hub re-scores the clip with
PANNs [6], the pretrained AudioSet tagging network (CNN14, or a
lighter checkpoint on a slow Pi). It takes the summed probability over
the distress-relevant AudioSet classes (screaming, shouting, yelling,
crying, wailing, and similar) as a distress score in [0, 1]. No
bespoke training is required; the hub relies on AudioSet scale, which
a locality Pi 5 can afford and a solar pole cannot. A labelled
energy-heuristic fallback backend (loud, high spectral centroid,
bursty) exists so the whole chain runs on any development machine. It
is not a claim of accuracy, and every result produced with it is
marked as fallback.

**Fusion.** A night-time scream in a dark spot with motion nearby
carries more weight than a daytime shout on a busy road. With a the
Stage-2 audio score, c the Stage-1 confidence, p ∈ {0,1} the PIR
motion flag, d = 1 − L/255 the darkness derived from the LDR level
L ∈ [0,255], and n ∈ {0,1} the night indicator (1 during
20:00 to 06:00), the fused severity is

> S = 0.60·a + 0.15·c + 0.10·p + 0.08·d + 0.07·n, (9)

with priority `high` at S ≥ 0.75 or verified audio (a ≥ 0.6)
together with PIR motion (p = 1). Dispatch requires **both** gates
to pass,

> dispatch ⟺ (a ≥ τ_v) ∧ (S ≥ τ_d), τ_v = 0.50, τ_d = 0.60; (10)

below either threshold the incident is logged with a human-readable
reasons trace and no drone flies. When the verification clip never
arrives (§3), the degraded audio score

> a = 0.6·c (11)

is substituted before applying (9) and (10). The gating is covered by
automated tests, and the weights in (9) are prototype values to be
tuned against Phase-1 bench data.

## 5. Secure LoRa Alerting

A spoofed packet would launch a drone; a replayed one would launch it
at a time the attacker chooses. Every alert is therefore a sealed
25-byte packet that fits in one LoRa frame, laid out as shown in
Figure 2: a cleartext header (magic, version, node_id uint16, counter
uint32), an 8-byte AES-128-CTR-encrypted payload (event class,
Stage-1 confidence, PIR flag, LDR level, node battery), and an 8-byte
MAC (HMAC-SHA256 over header + ciphertext, truncated).

![Figure 2: 25-byte sealed alert wire format](figures/v2/fig4_packet.png)

*Figure 2. The 25-byte sealed alert packet: cleartext header,
AES-128-CTR ciphertext, and truncated HMAC-SHA256 tag, all in one
LoRa frame.*

Per-node keys derive from the master key K_m by keyed hashing
(FIPS-197 AES, RFC 2104 HMAC [10]),

> K_n = HMAC-SHA256(K_m, "node:" ∥ n)[0:16], (12)

so provisioning needs only the master key and an id. A captured node
compromises one pole, and that node can be revoked in the registry.
The payload P is encrypted in CTR mode,

> C = P ⊕ E_{K_n}(IV), (13)

with the counter block IV built from the cleartext header
(magic ∥ ver ∥ node_id ∥ counter), which is unique per packet while
the counter is monotonic. Authentication is encrypt-then-MAC,

> τ = HMAC-SHA256(K_n, header ∥ C)[0:8]. (14)

The hub accepts a packet only when

> τ valid ∧ counter > counter_last, (15)

so bad MACs, unknown node ids, and replays are all rejected. Forging
the 64-bit truncated tag succeeds with probability 2⁻⁶⁴ per attempt.
Above the radio, the hub reaches the drone stack through the same
token-authenticated, geofence-validated API as any operator; there is
no privileged backdoor. Residual risk is stated: jamming can deny
service but cannot forge an alert; multi-node corroboration and
node-liveness monitoring are future answers.

The LoRa/WiFi split of §3 follows from the physics. LoRa's range
comes from spreading. Each symbol lasts

> T_s = 2^SF / BW, (16)

and the receiver sensitivity floor

> S_dBm = −174 + 10·log₁₀(BW) + NF + SNR_min (17)

drops below −120 dBm at high SF over BW = 125 kHz, so milliwatts
reach kilometres. The same trade caps throughput: the standard LoRa
time-on-air expression (Semtech SX127x datasheet [8]) gives ≈ 0.21 s
for the 25-byte sealed alert at SF9, BW 125 kHz, CR 4/5, explicit
header + CRC, whereas the 4 s clip (≈ 128 kB at ≈ 5.5 kb/s effective)
would occupy the channel for minutes. So the alert goes over LoRa and
the clip over ESP-NOW/WiFi.

Privacy is built into the design: continuous audio cannot leave a
node because the transport cannot carry it and the clip path is
event-gated in firmware. Only event-triggered clips ≤ 5 s are ever
transmitted, and the alert itself is encrypted.

## 6. Safety-Verified Drone Response

The response layer is our SITL-verified dispatch stack. Its three
mechanisms transfer intact. **Verified mode transition:** every
flight-mode command, nominal or emergency, routes through a single
routine. The routine re-issues the request through layered MAVLink
encodings (`COMMAND_LONG`/`MAV_CMD_DO_SET_MODE` plus the legacy
`SET_MODE`) every 700 ms until the autopilot's own HEARTBEAT-derived
mode confirms adoption, with a cross-action fallback (RTL ⇄ LAND) on
the abort path. This design answers the silent rejection we observed
on ArduCopter 3.3 SITL. **Landing interlock:** every abnormal
termination blocks until the vehicle demonstrably lands and disarms
(bounded 240 s) before the queue regains control, and a dequeued
mission refuses to arm an armed vehicle. Together, these mean the
queue can never start a flight against an airborne vehicle.
**Failsafe arbitration:** battery, GPS, geofence, and timeout monitors
feed a 1 Hz arbiter with monotone severity (LAND never downgraded),
N-sample GPS debounce, fire-once event semantics, and mid-RTL
escalation. Geofence radii, arrival detection against the 5 m waypoint
tolerance, and ETA all use the haversine great-circle distance

> d = 2R·arcsin √( sin²(Δφ/2) + cos φ₁·cos φ₂·sin²(Δλ/2) ),
> R = 6371 km. (18)

The thirteen-state mission FSM within which these mechanisms run is
shown in Figure 3.

![Figure 3: Thirteen-state mission state machine](figures/v2/fig5_state_machine.png)

*Figure 3. The 13-state mission FSM, from IDLE through TAKEOFF,
ENROUTE, HOVERING, and DELIVERING to RTL and LANDED, with the
abnormal paths into ABORTED and FAILED.*

v2 adds the response payload. The mission FSM (now thirteen states)
records camera evidence during the hover window (Pi Camera Module 3
on hardware; a no-op stub in SITL, so the flow is byte-identical) and
then enters **DELIVERING**: descend over the incident point to the
configured drop altitude (3.0 m, tolerance 0.7 m, bounded at 45 s),
release the first-aid kit via an SG90 servo on Pixhawk AUX OUT 1
commanded with `MAV_CMD_DO_SET_SERVO` (open 1900 PWM, 2 s settle,
re-close 1100), then climb back to cruise altitude for the RTL. The
3 m rule comes from simple ballistics: a kit released from height h
free-falls for

> t = √(2h/g) ≈ 0.78 s at h = 3 m, (19)

during which a v_w = 2 m/s wind drifts it only

> x ≈ v_w·t ≈ 1.6 m, (20)

keeping the kit within reach of the victim. A cruise-altitude release
would increase both drift and impact energy.
The governing rule is that **a failed release is never a reason to
loiter**: the failure is logged and the drone proceeds to RTL
regardless. The DELIVERING loop polls the failsafe arbiter like every
other phase, so a battery or GPS demand pre-empts the drop. All
prototype flying is VLOS-only on a registered airframe with an RC
safety pilot, per India's Drone Rules 2021 [5]; autonomous BVLOS
response is described strictly as a supervised pilot-program pathway.

## 7. Evaluation

### 7.1 Methodology

Validation is staged. **Tier 1:** 68 automated unit cases: 47 over
the flight stack's safety logic (every arbiter rule, queue semantics,
persistence, every edge-validation bound), 14 over the hub chain
(packet seal/unseal, MAC tamper rejection, replay rejection, registry,
fusion, pipeline gating, where *no dispatch below threshold* is
asserted rather than assumed, and dispatcher payload shape), and 7
over obstacle keep-out routing. The suites discriminate: run against
the pre-hardening implementation, the debounce, cancel, and interlock
cases fail. **Tier 2:** an eight-property SITL acceptance flight
(ArduCopter 3.3; 896 m mission at 15 m altitude): simulator up, API
up, connected, armed, took off, reached target (≤ 5 m), returned home
(≤ 10 m, required), landed. **Tier 3:** the Phase-0 full-chain
rehearsal (`scripts/demo_phase0.py`). A synthesized distress WAV
stands in for the microphone; a simulated node 600 m from home seals
a real packet with the production cryptography; the production hub
pipeline verifies (fallback backend), fuses, gates, and dispatches;
and the production drone stack flies the SITL mission with
hover-record and kit drop. Everything except the audio source, the
Stage-2 backend, and the physics is production code.

### 7.2 Results

Tier 1: **68/68 pass.** Tier 2: **8/8 checks pass.** Across six
acceptance missions spanning the development arc, closest approach was
0.4 to 0.6 m against the 5 m tolerance, and final distance from home
was 0.0 to 0.2 m; terminal accuracy is bounded by the autopilot's
loiter behaviour, not by the dispatch layer. Tier 3: the rehearsal
**passed end to end**. The sealed alert (event `scream`, PIR active,
dark LDR) was authenticated and replay-checked; the fallback backend
scored the clip above the 0.50 verification threshold; **fused
severity 0.88** (priority `high`) cleared the 0.60 dispatch gate; and
the SITL mission ran the full lifecycle with the recording window
active and **kit release commanded at 3.1 m** relative altitude,
completing in **328 s** with 0.4 m closest approach. Figure 4 shows
the rehearsal's altitude profile, with the descent to the 3.1 m
release point visible between the hover window and the return leg.

![Figure 4: Phase-0 rehearsal altitude profile with kit drop at 3.1 m](figures/v2/fig8_mission_profile.png)

*Figure 4. Altitude profile of the Phase-0 full-chain rehearsal:
takeoff to cruise, transit, hover-observe, descent to the 3.1 m kit
release, climb-out, and return to launch, completing in 328 s.*

### 7.3 What is measured vs. in progress

The Phase-0 result proves the architecture and the integration: every
interface a hardware phase will use (packet bytes, clip convention,
thresholds, trigger payload, servo command) was exercised in
production form. It deliberately proves nothing about acoustic
detection performance. **No Stage-1 accuracy exists.** The TFLM model
is a hook; training and flashing it is Phase 1; < 50 ms is a design
budget, not a measurement. **No field Stage-2 accuracy exists.** The
Phase-0 score came from the labelled heuristic fallback on synthesized
audio; PANNs' published performance [6] motivates the backend and is
not a field claim. For transparency, the fallback scorer is fully
specified: over the clip samples it computes the RMS level

> RMS = √( (1/N)·Σ x²[n] ), (21)

the spectral centroid

> C = Σ f·|X(f)| / Σ |X(f)|, (22)

and an envelope-burstiness term, combined as

> score = 0.45·min(1, RMS/0.15)
> + 0.35·clip((C − 400)/1600, 0, 1) + 0.20·burstiness. (23)

Equations (21) to (23) describe a labelled development stand-in
(loud, high-centroid, bursty audio scores high), not a detection
claim. **No radio range/loss or ESP-NOW reliability figures exist**
(Phase 2). **No hardware flight has occurred.** Phase 3's staged VLOS
progression governs the transition; the SITL firmware is the
2015-vintage 3.3 build, whose command-delivery faults forced the
defensive design. These measurements (outdoor detection distance vs.
SNR, per-stage latency, end-to-end false-positive rate on street
noise, LoRa range vs. spreading factor) are the explicit deliverables
of the Phase 1 and 2 bench campaigns and will appear in the journal
version once measured.

## 8. Regulatory, Spectrum, and Privacy Grounding

Deployment legality is part of the design. **Airspace:** UAS
operation in India is governed by The Drone Rules, 2021
(G.S.R. 589(E), Ministry of Civil Aviation) [5], which require
registration on the DGCA's Digital Sky platform and divide airspace
into green, yellow, and red zones. All prototype flying sits in the
least-restrictive cell of that framework: a registered airframe,
VLOS-only, in green-zone private airspace, with an RC safety pilot
holding override authority. Autonomous BVLOS response is framed
strictly as a supervised pilot-program pathway contingent on
regulatory approval, which the Rules and the DGCA BVLOS experiment
schemes provide. **Spectrum:** the prototype's SX1278 links operate
as low-power 433 MHz short-range devices; production would migrate to
the WPC-delicensed 865 to 867 MHz band [11], where higher power is
permitted licence-free and Indian LoRa deployments normally operate.
Neither band needs an operating licence at the power levels used.
**Privacy:** the Digital Personal Data Protection Act, 2023 [12]
requires purpose limitation, minimisation, and safeguards. The design
answers structurally: on-device processing, no continuous recording
or transmission, only event-triggered clips ≤ 5 s retained as
incident evidence, and encryption in transit. Compliance is then a
process on top of an architecture that already collects the minimum.

## 9. Conclusion

VanniKawachh integrates TinyML pole-side screening, pretrained deep
audio verification with environmental fusion, sealed operator-free
alerting, and a safety-interlocked autonomous first response into a
single women-safety chain that asks nothing of the victim but her
voice. The complete chain is demonstrated in simulation before any
hardware is committed. One rule governs every layer: a claim is not a
confirmation. A Stage-1 hit is not an incident until Stage 2 and
fusion say so; a packet is not an alert until its MAC and counter say
so; a mode command is not a mode until the autopilot's telemetry says
so; a mission is not finished until the vehicle is disarmed on the
ground. Under that rule the integrated rehearsal passed on the first
architecture, and the remaining work is measurement and hardening
rather than redesign. Future work: the Phase 1 and 2 measurement
campaigns; live RTSP/WebRTC streaming to police; OpenCV victim
tracking during hover; TDOA multi-node localization between poles;
and the city-scale node mesh with fleet dispatch.

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
  Rules, 2021, notification G.S.R. 589(E), The Gazette of India,
  25 Aug. 2021; DigitalSky platform.
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
- **[10] NIST FIPS-197** (AES); **RFC 2104** (HMAC: Keyed-Hashing for
  Message Authentication, Krawczyk, Bellare, Canetti, Feb. 1997).
- **[11] Wireless Planning and Coordination Wing, Department of
  Telecommunications, Government of India.** Gazette notification
  delicensing low-power wireless use of the 865-867 MHz band.
  <https://dot.gov.in/spectrum-management>. Accessed 2026-07-06.
- **[12] Government of India.** The Digital Personal Data Protection
  Act, 2023 (No. 22 of 2023), The Gazette of India, 11 Aug. 2023.
- **[S1]-[S12]** Literature-survey entries (twelve papers, 2023-2026)
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
