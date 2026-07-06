# VanniKawachh Hardware Phases (1 to 4)

Phase 0 (full chain in SITL) is done and passes. This guide is the step by
step procedure for the four hardware phases. Everything software side is
already in the repo; each phase below is mostly your hands on hardware plus a
few commands.

Rule for every flying step: fly VLOS in an open private field with the RC
transmitter in your hand as an override, and register the drone on Digital Sky
per the Drone Rules 2021.

---

## Phase 1 — Audio bench

Goal: get a trained Stage-1 model running on the ESP32-S3, verify with the Pi
hub, and measure real numbers (detection distance, latency, false triggers).

### 1.1 Bring the node up on the heuristic build first
This proves the wiring and the LoRa/WiFi paths before any model.
1. Wire the node per `docs/HARDWARE_INTEGRATION.md` Part A (INMP441 on
   WS=GPIO4, SCK=GPIO5, SD=GPIO6; SX1278 on the listed SPI pins; PIR on GPIO7;
   LDR on GPIO1).
2. Arduino IDE: board "ESP32S3 Dev Module", enable PSRAM ("OPI PSRAM").
   Libraries: LoRa (Sandeep Mistry).
3. Open `firmware/node/node.ino`, set `WIFI_SSID/PASS` and `HUB_CLIP_URL` to
   your hub, keep `MASTER_KEY` matching the hub. Flash.
4. Clap/shout near the mic: the serial monitor should print `STAGE-1 HIT`.

### 1.2 Collect real audio (this is the real deliverable)
The model is only as good as this data.
```
pip install sounddevice
python ml/record_samples.py --label background --count 200   # collect the MOST of this
python ml/record_samples.py --label scream     --count 120
python ml/record_samples.py --label help       --count 120   # "help", "bachao", "madad"
python ml/record_samples.py --label cry        --count 80
```
Record in the real deployment noise, with several people, at 3 to 20 m.
Supplement negatives with public sets (ESC-50, UrbanSound8K) copied into
`ml/data/background/`.

### 1.3 Train and export
Two paths; both read `ml/data/` and print per-class validation recall.

Path A (no heavy downloads, recommended to start). Trains a small MLP with
NumPy only and exports plain C. This is what runs today in this repo:
```
python ml/make_bootstrap_dataset.py          # stand-in data to prove the chain
python ml/train_stage1_numpy.py --epochs 400 # writes ml/out/stage1_nn.h + .npz
cp ml/out/stage1_nn.h firmware/node/          # already committed for the demo
```
Flash with `-DUSE_NN_STAGE1` (no TFLM library needed). A trained
`firmware/node/stage1_nn.h` is already in the repo so the node classifies
scream/help/cry out of the box.

Path B (bigger CNN, for production). Needs TensorFlow:
```
pip install tensorflow librosa soundfile
python ml/train_stage1.py --epochs 60
```
This writes `ml/out/stage1_int8.tflite` and `ml/out/stage1_model_data.cc`;
flash with `-DUSE_TFLM_STAGE1`. Or use Edge Impulse for guaranteed MFCC parity.

Either way, the bootstrap numbers only validate the pipeline. Real detection
performance needs the Phase-1 field recordings from step 1.2.

### 1.4 Evaluate the two stages
```
python ml/eval_pipeline.py --data ml/data
```
Records Stage-1 recall, the background reject rate, and Stage-2 score
separation. Put these numbers (from REAL data, not the bootstrap set) in the
paper's results table.

### 1.5 Flash the trained model onto the node
1. Copy `ml/out/stage1_model_data.cc` into `firmware/node/` as `model_data.cc`.
2. Add a TFLM library: Arduino "Chirale_TensorFlowLite" or Espressif
   "esp-tflite-micro".
3. Build with `USE_TFLM_STAGE1` defined (Arduino: add to
   `build_opt.h`/platformio `build_flags = -DUSE_TFLM_STAGE1`).
4. Confirm feature parity: `stage1.cpp`'s MFCC mirrors `ml/mfcc.py`. Before
   trusting it, print the node's MFCC for a known WAV and compare to
   `python -c "from ml.mfcc import mfcc; import soundfile,numpy; ..."`. If they
   diverge, do not deploy; use Edge Impulse instead (it guarantees parity).

Simpler alternative for the whole of 1.3 to 1.5: upload `ml/data/` to Edge
Impulse, let it train an MFCC + CNN, and export the Arduino library. It handles
feature parity for you.

### 1.6 Measure (write these down for the paper)
- Detection distance vs SNR: trigger a scream at 3, 5, 10, 15, 20 m; note the
  farthest reliable detection.
- Stage-1 latency: the node prints inference cadence; target under 50 ms/window.
- False triggers: run the node in real background for an hour; count alerts.

---

## Phase 2 — LoRa alert path

Goal: node to hub over real LoRa, no WiFi for the alert.

1. Flash `firmware/gateway/gateway.ino` to the gateway ESP32 (SX1278 on the
   pins in the sketch). Plug it into the Pi 5 over USB.
2. On the Pi 5:
   ```
   pip install -r requirements.txt -r requirements-hub.txt
   ```
3. Survey each pole once (phone GPS or the NEO-6M) and add it to
   `hub/nodes.json`:
   ```json
   { "1": { "lat": 21.1466, "lon": 79.0889, "name": "gate-north", "last_counter": 0 } }
   ```
   The `node_id` in the node firmware must match the key here, and the master
   key must match.
4. Run the hub against the gateway:
   ```
   python -m hub.main --serial /dev/ttyUSB0
   ```
   Open `http://<pi>:8990/` for the police dashboard.
5. Trigger a scream at the node. The hub log should show unseal, Stage-2 score,
   severity, and (if the drone API is up) a dispatch. The dashboard drops a
   marker and sounds the alarm.
6. Measure LoRa range and packet loss at SF7/SF9/SF12 in your environment; the
   25-byte alert is about 0.21 s on air at SF9.

Note: if you reflash a node (its NVS counter resets to 0), also reset that
node's `last_counter` to 0 in `hub/nodes.json`, or the hub will reject it as a
replay. This is the anti-spoofing check working as intended.

---

## Phase 3 — Drone build and flight

Goal: the response drone flying missions from the trigger API, with the
companion computer onboard.

### 3.1 Assemble (order matters)
1. F450 frame + motors + ESCs + power distribution; props OFF for now.
2. Pixhawk on vibration foam, arrow forward. GPS/compass (M8N) on a mast,
   arrow forward. Power module between battery and PDB.
3. RC receiver bound to the FlySky TX. SiK 433 telemetry on TELEM1.
4. Companion Pi (Zero 2 W) wired to TELEM2 UART; 5 V BEC to power it.

### 3.2 Configure the flight controller (Mission Planner or QGC)
1. Flash ArduCopter 4.x.
2. Frame type: Quad X. Load `docs/config/vannikawachh.param` (review every
   line; it sets telemetry, the payload servo, failsafes to match
   `flight_core/config.py`, and a geofence).
3. Calibrate: accelerometer, compass, radio, ESCs. Set flight modes with
   STABILIZE, LOITER, GUIDED, RTL on your switch.
4. Set battery failsafe voltages for your pack; confirm RTL on failsafe.

### 3.3 First flights (props on, open field, RC in hand)
1. Props-off arming test first: confirm arm/disarm and motor order/direction.
2. Props on: hover in STABILIZE, then LOITER. Confirm GPS lock and position
   hold.
3. Switch to GUIDED and command a short goto from Mission Planner. Keep the RC
   ready to retake control.

### 3.4 Bring in the stack
On the Pi: `git clone` the repo, install `requirements.txt`, then
```
setx MAVLINK_CONNECTION /dev/serial0     # UART to the FC
python -m uvicorn trigger_api.main:app --host 0.0.0.0 --port 8000
```
Send a trigger to a point 30 to 50 m away in the field and watch it fly the
mission with the RC as override. Do not enable `deliver_kit` yet.

---

## Phase 4 — Payload, camera, integration

1. Mount the SG90 servo with a printed hook holding the first-aid box. Wire the
   signal to Pixhawk AUX OUT 1 (servo output 9). `vannikawachh.param` sets
   `SERVO9_FUNCTION=0` (RC passthrough off) so `DO_SET_SERVO` from the stack
   drives it. Bench test: POST a trigger with `deliver_kit:true` to a grounded
   FC and confirm the servo opens then closes.
2. Mount the Pi Camera Module 3 on the companion. Install `picamera2`; the
   recorder writes `logs/recordings/<mission_id>.mp4` during the hover.
3. Drop test: hover at 3 m over a soft target and confirm the kit releases and
   the servo re-closes. Never drop from above 3 m.
4. Full field demo (film it): scream at a node, watch the hub confirm and
   dispatch, the drone fly out, hover and record, drop the kit, and return.
   This single run is the project's headline result.

Future work (papers, not the prototype): live video streaming to police
(RTSP/WebRTC over LTE), OpenCV victim tracking, multi-node TDOA localization.
