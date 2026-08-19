# VanniKawachh -- all run commands (together and apart)

Run everything from the project root: `D:\drone-safety-system`.

## Setup (do this once per terminal)

Use the project virtual environment -- it has every dependency (dronekit, SITL,
pytest, numpy). In PowerShell:
```
cd D:\drone-safety-system
.\.venv\Scripts\Activate.ps1        # now `python` = the venv python
```
If activation is blocked, just prefix commands with the venv python instead:
`.\.venv\Scripts\python.exe <script>`.

---

## A. RUN EVERYTHING TOGETHER

**1. The full chain in ONE command (SITL flight, no hardware)** -- the headline
demo: scream -> node -> hub -> verify -> fuse -> dispatch -> real SITL flight ->
kit drop -> return. Takes ~5 minutes.
```
python scripts/demo_phase0.py
```

**2. The live web system** (dashboard + sensor page + drone visualization):
```
python -m hub.main --web-only
```
Then open:
* `http://localhost:8990/`            -> police dashboard (map, detection pipeline, drones)
* `http://localhost:8990/node`        -> sensor node (SIMULATE DISTRESS / live mic)
* `http://localhost:8990/drone-phone` -> a phone acting as the drone

For the live microphone + GPS (needs HTTPS):
```
python -m hub.main --web-only --https
```
Live cloud version (always on): https://vannikawachh-hub.onrender.com/

---

## B. RUN EACH PART APART

**The trained model, on one clip** (scream vs silence):
```
python -c "import numpy as np; from ml.infer_nn import Stage1NN, CLASSES; m=Stage1NN(); sr=16000; t=np.arange(sr*2)/sr; s=0.5*np.sin(2*np.pi*(900+500*np.sin(2*np.pi*2.6*t))*t); s[int(.6*sr):int(1.5*sr)]*=2; k,c=m.infer(s); print('scream ->', CLASSES[k], round(c,2)); k,c=m.infer(np.zeros(sr*2)); print('silence ->', CLASSES[k], round(c,2))"
```

**Train the Stage-1 model** (loads ml/data, trains, exports the weights):
```
python ml/train_stage1_numpy.py
```

**Evaluate the two-stage detector** (per-class recall + Stage-2 scores):
```
python ml/eval_pipeline.py
```

**Regenerate the dataset** (writes 560 clips into ml/data/):
```
python ml/make_bootstrap_dataset.py
```

**Train the real CNN on a GPU** (Colab / Kaggle / Lightning -- see
docs/DATASET_AND_TRAINING.md):
```
python ml/train_gpu.py --epochs 40
```

**Simulate a hardware node hitting the hub** (what the Wokwi ESP32 does) --
start the web system first, then:
```
curl "http://localhost:8990/node-alert?node=TEST&lat=21.1466&lon=79.0889&event=1&conf=0.92&pir=1&light=20"
```

---

## C. TESTS (proof it's solid)

All suites:
```
python -m pytest -q
```
Just one (fast):
```
python -m pytest -q tests/test_mfcc.py          # MFCC front-end
python -m pytest -q tests/test_stage1_nn.py     # the model
python -m pytest -q tests/test_hub.py           # packets / fusion / dispatch
python -m pytest -q tests/test_obstacle_avoidance.py
python -m pytest -q tests/test_phone_mode.py    # end-to-end web pipeline
```
(These need the venv -- plain `python` may not have pytest.)

---

## D. HARDWARE SIMULATION (Wokwi -- in the browser)

1. Open your dashboard first: https://vannikawachh-hub.onrender.com/
2. Go to wokwi.com -> New Project -> ESP32.
3. Paste `sim/wokwi/vannikawachh-node-cloud/diagram.json` and `sketch.ino`.
4. Press Play, then press the red SCREAM button -> the simulated ESP32 alerts
   your live dashboard over WiFi and a drone dispatches.

Other Wokwi projects: `sim/wokwi/vannikawachh-system/` (one board detects and
runs the drone on-board), `sim/wokwi/vannikawachh-node/` + `-drone/` (separate
boards). Tinkercad (real DC motors): `sim/tinkercad/`.

---

## E. DEPLOY (already live)

The dashboard auto-deploys to Render on every `git push`. Manual redeploy: push
to the repo. Config for it: `render.yaml`, `Dockerfile`, `requirements-deploy.txt`.

---

## Quick reference -- which command proves what

| To prove... | Command |
|---|---|
| The model decides on audio | the one-liner (B, first) |
| Training works | `python ml/train_stage1_numpy.py` |
| Detection accuracy (pipeline) | `python ml/eval_pipeline.py` |
| The whole chain + real flight | `python scripts/demo_phase0.py` |
| The live system + dashboard | `python -m hub.main --web-only` |
| Hardware drives the system | Wokwi cloud node -> dashboard |
| Code quality | `python -m pytest -q` |
