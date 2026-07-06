# VanniKawachh — Project Plan (v2 concept)

**A Distributed AI Acoustic Intelligence and Autonomous Drone Response Network
for Women Safety.**
Group CSE_B_04 · GHRCE Nagpur · Session 2026–27 · Guide: Dr. Aditya Turankar

This document is the master plan. It supersedes the v1 "generic trigger →
drone" framing: the drone-safety stack built and SITL-verified in v1 is now
the **response layer** of VanniKawachh; the new work is the **sensing layer**
(acoustic nodes + hub) that generates the trigger, and the **response payload**
(evidence camera + first-aid drop).

---

## 1. Concept in one paragraph

Solar-powered microphone nodes on poles in high-risk public spots (dark
streets, forest stretches, campus outskirts, parking areas) listen 24×7. Each
node's ESP32-S3 screens every audio frame on-device with a lightweight
MFCC + CNN model (Stage 1, < 50 ms, high recall). Distress-like events are
verified at a Raspberry Pi 5 hub running PANNs deep audio analysis fused with
PIR motion, LDR light and time-of-day evidence (Stage 2, high precision). A
confirmed alert — AES-128-encrypted, carrying the node's surveyed GPS
coordinates — travels over LoRa (no SIM, no cellular) to the police dashboard
and simultaneously auto-dispatches a Pixhawk quadcopter that flies to the
spot, records evidence, drops a first-aid kit, and (future work) streams live
video to authorities. The victim needs no phone, no app, no wearable — her
voice is the trigger.

## 2. Why the two-stage design (research grounding)

The literature survey (12 papers, 2023–2026 — see the Title Finalization
Seminar deck and `RESEARCH_PAPER.md` references) shows every prior system
falls in one of two buckets:

1. **Victim-carried devices** (apps, wearables, panic buttons — refs [1], [5],
   [6], [9], [10], [11]): fail when the device is absent, damaged, discharged,
   or unreachable in the moment. Accuracies up to 97.5% are reported, but the
   trigger burden stays on the victim.
2. **Detection-only audio systems** (refs [2], [3], [4], [7], [8]): scream
   detection reaches 92–95.5% (CNN-Transformer, InceptionV3/MobileNetV2 on
   mel-spectrograms), but they are compute-heavy (server-scale), device-bound,
   and stop at detection — no location delivery, no field response.

VanniKawachh's contribution is the **end-to-end chain**: infrastructure-mounted
sensing (no victim burden) → two-stage edge/hub verification (deployable on
low-power nodes, false alarms suppressed) → offline alert delivery (LoRa dead-
zone coverage) → autonomous first response (drone before ground units). The
two-stage audio pipeline deliberately mirrors the flight stack's "verified
dispatch" philosophy (Patent 1): *a detection claimed is not a detection
confirmed*, at every layer — sound, dispatch, and flight mode.

## 3. System architecture

```
┌────────────── SENSING NODE (per pole, solar) ──────────────┐
│ INMP441 I2S mic → ESP32-S3: MFCC + tiny CNN (TFLM, <50 ms) │
│ PIR (HC-SR501) + LDR context · Stage-1 hit → alert + clip  │
└──────────────┬─────────────────────────────┬───────────────┘
        LoRa SX1278 (alert, AES-128)   ESP-NOW / WiFi (4 s audio clip)
               ▼                             ▼
┌────────────── HUB (Raspberry Pi 5, per locality) ──────────┐
│ LoRa gateway (ESP32 + SX1278 on USB serial)                │
│ Stage 2: PANNs (CNN14/CNN10) + PIR/LDR/time fusion score   │
│ Node registry: node_id → surveyed (lat, lon)               │
│ Police dashboard (live map + alarm) · alert log            │
└──────────────┬─────────────────────────────────────────────┘
         POST /trigger {lat, lon, incident_type, priority}
               ▼
┌────────────── RESPONSE DRONE (v1 stack, unchanged core) ───┐
│ trigger_api (FastAPI queue) → mission_executor (12-state   │
│ FSM, verified mode setter, failsafe arbiter, landing       │
│ interlock, obstacle keep-out routing)                      │
│ NEW: HOVER+record (camera) → DELIVERING (SG90 kit drop)    │
│      → RTL · live stream to police = future work           │
└────────────────────────────────────────────────────────────┘
```

Key design decisions (and why):

- **Fixed nodes don't carry live GPS.** Each pole is surveyed once at install
  (NEO-6M or phone); the hub's registry maps `node_id → (lat, lon)`. LoRa then
  only needs to carry a few bytes, not coordinates from a live fix.
- **LoRa cannot carry audio** (~1–5.5 kbps effective). The alert goes over
  LoRa instantly; the 4 s verification clip goes over ESP-NOW/WiFi (~250 kbps,
  hundreds of metres LOS). If the clip never arrives, the hub can still act on
  multi-node corroboration or dispatch at reduced confidence.
- **Stage 1 is recall-tuned, Stage 2 is precision-tuned.** The node model is a
  TFLM `micro_speech`-class CNN over MFCCs detecting scream / cry /
  "help" / "bachao" keywords; the hub runs PANNs (pretrained AudioSet CNN;
  use CNN10 or a MobileNet variant if CNN14 is too slow) plus the sensor-
  fusion score (PIR motion + darkness + time-of-day raises severity).
- **AES-128-CTR on every LoRa packet** — alerts must be unreadable and
  unforgeable (a spoofed packet would launch a drone).
- **The flight core is untouched.** All v1 safety machinery (verified setter,
  failsafe arbiter, landing interlock, geofence, stall detection, obstacle
  keep-out routing) carries over unchanged — it is the reason the drone half
  of this project already works.

## 4. Repository layout (v2)

```
drone-safety-system/
├── flight_core/          # v1 flight stack + NEW: payload_release, camera_recorder
├── trigger_api/          # v1 FastAPI dispatch surface (unchanged API)
├── hub/                  # NEW — Stage-2 hub service (Pi 5)
│   ├── config.py           # env-driven hub settings
│   ├── node_registry.py    # node_id → lat/lon/meta (JSON-backed)
│   ├── packets.py          # LoRa packet format + AES-128 seal/unseal
│   ├── lora_gateway.py     # serial reader for the ESP32 LoRa gateway (+ sim mode)
│   ├── verifier.py         # Stage-2: PANNs backend or energy-heuristic fallback
│   ├── fusion.py           # PIR/LDR/time severity fusion
│   ├── pipeline.py         # alert → verify → fuse → dispatch decision
│   ├── dispatcher.py       # POSTs /trigger to the drone stack
│   └── main.py             # hub entrypoint (serial or --sim)
├── firmware/             # NEW — ESP32 sketches
│   ├── node/               # sensing node (I2S mic, MFCC+TFLM hook, PIR/LDR, LoRa TX, clip upload)
│   └── gateway/            # hub-side LoRa RX → USB serial bridge
├── dashboard/            # v1 viewer (extend with alert layer later)
├── tests/                # unit + e2e (test_hub.py NEW)
├── scripts/demo_phase0.py  # NEW — full-chain SITL demo, zero hardware
└── docs/                 # this plan + updated docs
```

## 5. Build phases

### Phase 0 — full chain in SITL, zero hardware  ✅ implemented
Simulated node alert (WAV or synthesized scream) → hub pipeline (fallback
verifier if PANNs not installed) → registry lookup → POST /trigger → SITL
drone flies the mission with hover-record (no-op recorder) and DELIVERING
(servo command logged by SITL). Deliverable: `scripts/demo_phase0.py` demo
video for the seminar. **This proves the architecture before any soldering.**

### Phase 1 — audio bench (2–3 weeks)
ESP32-S3 + INMP441 capturing I2S audio; TFLM Stage-1 model flashed
(`firmware/node/`); clips over WiFi to the Pi 5; PANNs verification
(`pip install panns-inference torch` on the Pi). **Measure and record:**
real outdoor detection distance vs. SNR, Stage-1 latency (< 50 ms target),
Stage-2 latency, end-to-end false-positive rate on street noise. These
numbers go in the paper.

### Phase 2 — LoRa alert path (1–2 weeks)
Gateway ESP32 (`firmware/gateway/`) on the Pi's USB. Node sends AES-128
sealed alert over SX1278; hub unseals, looks up the registry, runs the
pipeline. Measure range (urban / open) and packet loss vs. spreading factor.

### Phase 3 — drone build + manual→guided flights (3–4 weeks)
F450 frame, Pixhawk 2.4.8, M8N GPS+compass, 4×BLDC+ESC, 3S/4S LiPo, RC
transmitter (mandatory safety override), SiK 433 telemetry, Pi Zero 2 W
companion running the v1 stack (`MAVLINK_CONNECTION=/dev/serial0`).
Order: bench test → props-off arming → manual hover → GUIDED test with RC
override in hand → full auto mission in an open private field, VLOS only
(Drone Rules 2021: registration required; autonomous BVLOS = paper future
work, not prototype flying).

### Phase 4 — payload + camera + integration (2 weeks)
SG90 release servo on AUX (MAV_CMD_DO_SET_SERVO — implemented in
`flight_core/payload_release.py`), Pi Camera Module 3 recording during
hover (`flight_core/camera_recorder.py`, mp4 tagged with mission id),
drop from ≤3 m hover. Then the integrated field demo: scream → node →
hub → drone → kit drop, one take, filmed.

### Explicitly future work (papers/journals, not prototype)
Live video streaming to police (RTSP/WebRTC over LTE), OpenCV victim
tracking/follow, multi-node TDOA localization, BVLOS pilot-program
operation, city-scale node mesh.

## 6. Hardware BOM

**Per sensing node:** ESP32-S3 dev board, INMP441 I2S mic, HC-SR501 PIR,
LDR + divider, SX1278 LoRa + 433 MHz whip, 18650 Li-ion + TP4056 + 5 V
solar panel, weatherproof enclosure.

**Hub:** Raspberry Pi 5 (27 W PSU, active cooler, 64 GB SD), gateway
ESP32 + SX1278 on USB serial.

**Drone:** F450 frame + 1045 props (+ spares), Pixhawk 2.4.8, M8N GPS +
compass, 4× 2212 920KV BLDC, 4× 30 A ESC, 3S/4S LiPo + balance charger +
battery alarm, power module, FlySky FS-i6 RC TX/RX, SiK 433 telemetry
pair, Pi Zero 2 W + 5 V BEC, Pi Camera Module 3, SG90 servo + printed
release hook, landing gear.

Already owned per the seminar deck: Pi 5, ESP32, INMP441, PIR, LDR,
NEO-6M (use for node surveys), SX1278 ×2, batteries, Pixhawk, BLDC, ESCs.
Still to acquire: frame/props, LiPo+charger, power module, M8N GPS, RC
set, SiK pair, Pi Zero 2 W, camera, SG90 (~₹15–25k).

## 7. Safety, privacy, legal (state everywhere, verbatim if needed)

- **Privacy:** no continuous recording or transmission. Audio is processed
  on-device; only event-triggered clips ≤ 5 s leave a node, encrypted.
- **Flight law:** prototype flights are VLOS, open private field, RC
  override in hand, drone registered per Drone Rules 2021. Autonomous
  BVLOS response is described as a supervised pilot-program pathway.
- **Payload:** kit drop only from ≤ 3 m hover; release failure → RTL and
  report (never loiter on a failed drop).
- **Spoofing:** every LoRa packet AES-128 sealed with per-node keys and a
  monotonic counter (replay protection); unknown node_id or bad MAC ⇒ drop.

## 8. Test strategy

- `tests/test_units.py` — v1 safety logic (failsafes, queue, validators) ✅
- `tests/test_obstacle_avoidance.py` — keep-out routing geometry ✅
- `tests/test_hub.py` — NEW: packet seal/unseal + replay, registry, fusion
  scoring, pipeline gating (no dispatch below threshold), dispatcher payload
- `tests/test_full_mission.py` — v1 e2e SITL flight ✅
- `scripts/demo_phase0.py` — full-chain rehearsal (sensing sim → flight)
```
Every safety claim in the paper must be pinned by one of these before it
is written down.
```
