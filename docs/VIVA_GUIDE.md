# VanniKawachh -- project defense / viva guide

Everything you need to explain and defend the project today. Plain language,
exact files, exact formulas, the "why this not that" answers, how to run each
piece live, and an honest done-vs-pending list so nothing catches you out.

---

## 0. The 30-second pitch (say this first)

"VanniKawachh is a women-safety network. Small, cheap sound sensors on roadside
poles listen for distress -- a scream or a shout for help. When one is detected
and verified, the system automatically sends the nearest drone to the exact
location with a first-aid kit and a camera, with no human in the loop and no
internet needed for the alert. It buys the critical minutes before help
arrives."

## 1. What is actually built (your proof of progress)

| Layer | What it does | Where the code is | Status |
|---|---|---|---|
| Node firmware | reads mic, runs Stage-1 detection, sends sealed alert | `firmware/node/` | written, runs in sim |
| Stage-1 model | MFCC + small neural net, classifies scream/help/cry/background | `ml/`, `firmware/node/stage1.cpp` | trained (on bootstrap data), runs |
| Hub service | verifies (Stage-2), fuses evidence, decides, dispatches | `hub/` | working end to end |
| Fleet + dispatch | picks nearest drone station, computes ETA | `hub/sim_drone.py` | working |
| Flight | autonomous mission: takeoff -> fly -> drop kit -> return | `flight_core/` | flies in ArduPilot SITL |
| Dashboard | live map, incidents, detection pipeline, drones | `hub/webapp.py` | deployed live on Render |
| Hardware sim | ESP32 in Wokwi drives the live dashboard | `sim/` | working |
| PCB design | sensing-node board for fab | `docs/EASYEDA_BUILD.md` | build sheet ready |
| Papers | journal, thesis, research paper, 2 patents | `docs/` | drafted |
| Tests | 7 test suites (mfcc, model, hub, flight, phone mode...) | `tests/` | passing |

**One-line honest summary:** the entire software system works end to end today;
the hardware is designed and simulated and this review is to fund building it.

## 2. How it works, end to end (the story)

1. **Sense.** A pole node (ESP32-S3 + INMP441 microphone) listens continuously.
2. **Stage-1 detect (on the node).** It turns 2 seconds of sound into MFCC
   features and runs a small neural net. Tuned for **recall** -- catch every
   possible scream, even at the cost of some false alarms. `firmware/node/`.
3. **Alert (LoRa).** If distress is suspected, the node sends a tiny **sealed**
   radio packet (node id, GPS, event, confidence) over **LoRa 433 MHz** -- no
   internet. The 2-second audio clip goes over WiFi/ESP-NOW to the hub.
4. **Stage-2 verify (on the hub).** A Raspberry Pi 5 runs **PANNs** (a model
   pretrained on Google's AudioSet) on the clip. Tuned for **precision** -- kill
   false alarms. `hub/verifier.py`.
5. **Fuse.** Combine the audio score with motion (PIR), darkness (LDR), and time
   of night into one **severity** number. `hub/fusion.py`.
6. **Decide + dispatch.** If severity crosses the threshold, the hub picks the
   **nearest drone station** and sends the target. `hub/sim_drone.py`,
   `hub/pipeline.py`.
7. **Fly + deliver.** ArduPilot flies the drone to the coordinates, drops the
   first-aid kit (a servo), records video, and returns. `flight_core/`.
8. **Dashboard.** Police see it all live on a map. `hub/webapp.py`.

## 3. Why this, not that (the questions they WILL ask)

**Why two stages instead of one?**
A node must be cheap and low-power (there are many of them on poles), so it can
only run a tiny model -- good enough to *catch* distress (high recall). The hub
is one powerful computer, so it runs a heavy, accurate model to *confirm* (high
precision) and reject false alarms. Cheap-and-sensitive at the edge, smart-and-
strict at the centre. This is a standard cascade design.

**Why ESP32-S3 at the node (not Arduino, not a Pi)?**
Arduino Uno is far too weak to compute MFCC + a neural net. A Raspberry Pi per
pole is too expensive and power-hungry to run on a small battery/solar. The
ESP32-S3 is the sweet spot: cheap (~Rs 500), low power, has hardware I2S for the
mic, and enough compute + an AI instruction set for a small CNN.

**Why MFCC features (not raw audio)?**
MFCC is the standard compact representation of sound for speech/audio ML. It
throws away what doesn't matter and keeps the shape of the sound, so a tiny
model can learn from it and it's cheap to compute on a microcontroller. Code:
`ml/mfcc.py` (and the C mirror in `firmware/node/`).

**Why PANNs for Stage-2?**
PANNs is pretrained on AudioSet (~2 million YouTube clips) and already knows
classes like "screaming", "shouting", "crying". We don't have to train it from
scratch -- we just sum the probabilities of the distress-related classes. Strong
and free. `hub/verifier.py`.

**Why LoRa for the alert (not 5G / WiFi)?**
The alert must work with **no internet**, over **long range**, on **low power**,
and cheaply. LoRa 433 MHz does kilometres on a coin-cell budget and is licence-
free. 5G needs coverage, a SIM, recurring cost, and more power -- and fails
exactly where safety matters (dead zones, disasters). The alert packet is tiny
(25 bytes), so LoRa's low bitrate is a non-issue. The bigger audio clip uses
WiFi/ESP-NOW only for the short node-to-hub hop.

**Why GPS positioning (not cell-tower / 5G location)?**
Each pole node has a **fixed, surveyed GPS coordinate** -- so we know the
victim's location exactly and instantly, with zero fix delay. The drone uses
GNSS + the Pixhawk EKF, which is metre-accurate and works offline. Cell-tower
location is tens-to-hundreds of metres off.

**Why Pixhawk + ArduPilot (not build our own flight controller)?**
It's the industry-standard open flight stack, with a software simulator (SITL)
so we test flight logic with no aircraft, MAVLink for control, and mature
failsafes (battery, GPS-loss, geofence). Reinventing this would be reckless.

**Why encrypt the packets (AES + HMAC)?**
A fake packet would launch a real drone. So every packet is authenticated
(HMAC-SHA256) and encrypted (AES-128), with a per-node counter so an attacker
can't record and replay an old alert. `hub/packets.py`.

**Why a drone + first-aid kit (not just call police)?**
The drone reaches the victim in the gap before humans can -- delivering a kit,
a camera (evidence + situational awareness), and a visible deterrent. It
complements, not replaces, the human response.

## 4. The formulas (know these three cold)

**MFCC front-end** (`ml/mfcc.py`): 16 kHz, 2 s window.
pre-emphasis `x[n] - 0.97 x[n-1]` -> frames (512 samples, hop 256, Hamming) ->
power spectrum `|FFT|^2` -> 40 triangular **mel** filters -> `log(energy)` ->
**DCT-II**, keep 13 coefficients. Output = 123 frames x 13 = the feature image.

**Stage-1 model** (`ml/infer_nn.py`, `ml/train_stage1_numpy.py`):
pool the MFCC image to per-coefficient **mean + std** = 26 numbers ->
standardise -> Dense 26->24 with **ReLU** -> Dense 24->4 with **softmax**.
Softmax: `p_i = e^{z_i} / sum_j e^{z_j}`. Output = probability of
{background, scream, cry, help}.

**Severity fusion** (`hub/fusion.py`) -- memorise this weighted sum:
```
severity = 0.60*audio + 0.15*stage1_conf + 0.10*PIR + 0.08*darkness + 0.07*night
```
audio (Stage-2) dominates; the rest nudge it. Dispatch if audio >= 0.50 AND
severity >= 0.60. Priority = "high" if severity >= 0.75 (or a loud scream with
motion). Say clearly: "these weights are prototype values, to be tuned on real
Phase-1 data" -- that is the honest and correct answer.

**Bonus:** distance between two GPS points is the **haversine** formula
(`hub/sim_drone.py` `_haversine_m`); ETA = distance / cruise speed.

## 5. How to RUN each piece live (demo commands)

**A. Run the trained model on its own** (they often ask this):
```
python -c "import numpy as np; from ml.infer_nn import Stage1NN, CLASSES; m=Stage1NN(); \
sr=16000; t=np.arange(sr*2)/sr; s=0.5*np.sin(2*np.pi*(900+500*np.sin(2*np.pi*2.6*t))*t); s[int(.6*sr):int(1.5*sr)]*=2; \
k,c=m.infer(s); print('scream ->', CLASSES[k], round(c,2)); \
k,c=m.infer(np.zeros(sr*2)); print('silence ->', CLASSES[k], round(c,2))"
```
Shows the real model classifying a scream vs silence.

**B. Run the whole system + dashboard:**
```
python -m hub.main --web-only
```
Open http://localhost:8990/ (dashboard) and http://localhost:8990/node (sensor).
Trigger SIMULATE DISTRESS -> watch the detection pipeline light up and the
nearest drone fly and drop the kit. Live version: https://vannikawachh-hub.onrender.com/

**C. The hardware simulation (Wokwi -> live dashboard):**
Open the deployed dashboard, then run the Wokwi ESP32 (`sim/wokwi/vannikawachh-node-cloud/`),
press the SCREAM button -> the simulated chip alerts the real dashboard over WiFi.

**D. Real autonomous flight in the simulator (ArduPilot SITL):**
```
python scripts/demo_phase0.py
```
Watch the drone arm, take off, fly to the coordinates, drop, and return -- the
same firmware that runs on a real Pixhawk.

**E. Run the tests (proof it's solid):** use the project's venv (it has pytest):
```
.venv/Scripts/python.exe -m pytest -q     # Windows
# or: source .venv/bin/activate && pytest -q
```
7 suites: mfcc, model, hub, flight, obstacle avoidance, phone mode. If you only
want a quick one: `.venv/Scripts/python.exe -m pytest -q tests/test_mfcc.py`.
(The plain `python` may not have pytest -- the `.venv` does.)

## 6. Where every piece of code lives (file map)

* Audio features: `ml/mfcc.py` (+ C mirror in `firmware/node/`)
* Train the model: `ml/train_stage1_numpy.py` (no GPU), `ml/train_gpu.py` (real data, GPU)
* Run the model: `ml/infer_nn.py`
* Node firmware: `firmware/node/node.ino`, `stage1.cpp`
* Packet security (AES+HMAC+replay): `hub/packets.py`
* Stage-2 verify (PANNs / fallback): `hub/verifier.py`
* Evidence fusion: `hub/fusion.py`
* Decision pipeline: `hub/pipeline.py`
* Fleet + nearest-drone + ETA: `hub/sim_drone.py`
* Dashboard + pages + APIs: `hub/webapp.py`
* Flight state machine: `flight_core/mission_executor.py`
* Obstacle avoidance: `flight_core/obstacle_avoidance.py`
* Kit release: `flight_core/payload_release.py`
* Failsafes: `flight_core/failsafe_handler.py`
* Hardware wiring / PCB: `docs/HARDWARE_WIRING.md`, `docs/EASYEDA_BUILD.md`
* Dataset + training plan: `docs/DATASET_AND_TRAINING.md`

## 7. Extra answers they like to dig into

**How does obstacle avoidance work? Where's the code?**
`flight_core/obstacle_avoidance.py`. It's **deterministic map-based** avoidance:
operators define circular keep-out zones; if a straight leg would pass too close
to one, the code inserts two detour waypoints to route around it at a safe
offset. Be honest: this is **known-map** avoidance, not sensor-based reactive
avoidance -- reactive (rangefinder / depth camera + ArduPilot OA) is on the
roadmap. It's pure geometry and unit-tested (`tests/test_obstacle_avoidance.py`).

**How does the kit actually drop?**
`flight_core/payload_release.py` sends a MAVLink `DO_SET_SERVO` to a servo on a
Pixhawk AUX output at the drop point -- the servo opens the release hook. Safety
rule: a failed release never blocks the return-to-home.

**What are the flight phases?**
`mission_executor.py` state machine: IDLE -> ARMED -> TAKEOFF -> GUIDED (goto) ->
HOVER -> DELIVER -> RTL -> LAND -> DONE. Every transition is logged; no phase
ever waits for a human.

**How is a false alarm prevented?**
Three gates: Stage-1 recall at the node, Stage-2 precision at the hub, then the
fusion threshold. Only when all agree does a drone launch.

## 8. HONEST done-vs-pending (say these yourself -- it builds trust)

**Done and demonstrable today:**
* Full pipeline: detect -> verify -> fuse -> dispatch -> autonomous SITL flight
  -> kit drop, live on a dashboard.
* Two-stage detection, evidence fusion, AES-secured packets, multi-drone
  nearest-dispatch, deployed cloud dashboard, Wokwi hardware sim driving it,
  7 passing test suites, PCB design, papers + patents drafted.

**Honestly still pending (don't hide these):**
* The Stage-1 model is trained on **synthetic + text-to-speech bootstrap
  audio**, not real distress recordings -- so its accuracy number is a
  pipeline check, not a field result. The real-data GPU training script is
  ready (`ml/train_gpu.py`, `docs/DATASET_AND_TRAINING.md`); collecting a real
  dataset is the next step.
* PANNs runs on the Pi in production; locally an energy-heuristic fallback
  stands in (labelled as such) because the torch model isn't installed here.
* The **hardware isn't physically built yet** -- that's exactly what this
  review's seed money is for. Everything is designed, wired, simulated, and the
  flight code is validated in SITL, so building is assembly, not invention.

If a professor pushes on accuracy: "The architecture and the whole pipeline are
proven. The honest gap is a real labelled dataset, which needs field recording
and GPU training -- the tooling for both is already written. I did not want to
report a fake accuracy from synthetic data."

## 9. Your 3-minute live demo order

1. `python -m hub.main --web-only` -> show `/node` trigger a scream -> dashboard
   detection pipeline lights up -> nearest drone flies + drops kit.
2. Run the model standalone (command 5A) -> "here's the actual model deciding."
3. Wokwi cloud node -> press SCREAM -> the simulated ESP32 drives the live
   dashboard. "This is the hardware, in simulation, running the real firmware."
4. `python scripts/demo_phase0.py` -> "and this is the real flight code flying
   the mission in ArduPilot's simulator."
5. Show `docs/HARDWARE_WIRING.md` + `docs/EASYEDA_BUILD.md` -> "here's the exact
   board we'll fabricate with the seed money."

Breathe. You built a real, working, end-to-end system. Walk them through it in
this order and answer "why" with section 3. You've got this.
