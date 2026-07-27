# Dataset Collection and Training Protocol (Stage-1 distress detector)

This is the plan for turning the current proof-of-pipeline model into a real,
publication-grade distress detector. The synthetic/TTS bootstrap only proves
the plumbing; real accuracy needs real audio and a proper GPU training run.

Do the training on a GPU (Google Colab, Kaggle, or a Lightning AI instance).
`ml/train_gpu.py` is the turnkey script; see "Running the training" below.

---

## 1. Classes

| index | class | what it is | fires the drone? |
|---|---|---|---|
| 0 | background | traffic, crowd, wind, music, normal talking, silence | no |
| 1 | scream | human screams / shouts of fear | yes |
| 2 | cry | distress crying, sobbing, wailing | yes |
| 3 | help | spoken calls: "help", "bachao", "madad", "save me" | yes |

Start here. You can collapse to binary (distress vs background) if data is thin;
report whichever you actually trained.

## 2. Where the audio comes from

**A. Public datasets (real recordings, no fieldwork needed to start).**
`ml/train_gpu.py` can pull these automatically:

* **ESC-50** (auto-download, no login) — 2000 clips, 50 environmental classes.
  Use its non-speech classes as `background`, and `crying_baby` toward `cry`.
* **A Kaggle scream dataset** (needs your `kaggle.json` API token) for the
  `scream` class, e.g. a "scream / non-scream" audio dataset. The script reads
  `~/.kaggle/kaggle.json` if present.
* **UrbanSound8K** (optional, form download) — extra urban `background`.
* **RAVDESS / CREMA-D** (optional) — emotional speech, useful negatives and to
  harden against "loud but not distress".

**B. Your own field recordings (this is what makes it deployment-real).**
Public data is clean and Western; your streets are not. Record with
`ml/record_samples.py` in the actual deployment noise:

```
python ml/record_samples.py --label background --count 300   # collect the MOST
python ml/record_samples.py --label scream     --count 150
python ml/record_samples.py --label help       --count 150   # help / bachao / madad
python ml/record_samples.py --label cry        --count 100
```

Recording conditions that matter (write these in the paper's methods):
* **Multiple people** (at least 8-10), mixed gender and age.
* **Distance** 3, 5, 10, 15, 20 m from the mic (matches the pole scenario).
* **Indoor and outdoor**, day and night.
* **Real background** captured on-site: traffic, horns, crowd, wind, music,
  ordinary conversation. Over-collect background; false alarms come from here.
* **Different phones/mics** so the model doesn't overfit one device.

Target for a first credible model: **>= 300 background, >= 200 each positive**,
mixed public + field. More is better; distress detection is hard and imbalanced.

## 3. Preprocessing (must match the firmware)

* 16 kHz mono, 2.0 s windows (`ml/mfcc.py` constants).
* Trim/pad to 2 s; peak-normalise.
* Features: the shared MFCC (`ml/mfcc.py`) so the ESP32 computes the same thing.
  For the CNN the input is the full MFCC matrix (frames x 13), not the pooled
  vector.

## 4. Augmentation (train set only)

* Gain +/- (0.5x to 1.4x), time shift, small pitch/time stretch.
* **Noise mixing**: add real background at random SNR (0-20 dB) to positives.
  This is the single most important augmentation for false-alarm robustness.
* **SpecAugment** (mask time/frequency bands) if using spectrogram CNNs.
* Room reverb (optional) to simulate outdoor/indoor.

## 5. Splitting (avoid leakage - reviewers check this)

* Split **by speaker and by recording session**, never by random clip. Clips of
  the same person/scene in both train and test inflates accuracy.
* Hold out at least one environment entirely for test.
* Suggested: 70% train / 15% val / 15% test, speaker-disjoint.
* Keep a separate **continuous background recording** (10-30 min of real street
  noise, never used in training) to measure false alarms per hour.

## 6. Model

* **Stage-1 (on the ESP32)**: small CNN over the MFCC matrix (a few conv layers
  + global pooling + dense + softmax), int8-quantised to TFLite for TFLM. Must
  stay under the node's arena (tens of KB). `ml/train_gpu.py` builds and exports
  this. Recall-tuned (catch distress; the hub filters false alarms).
* **Stage-2 (on the Pi hub)**: PANNs (pretrained on AudioSet). Either use it
  zero-shot (sum distress-class probabilities, already in `hub/verifier.py`) or
  fine-tune its last layers on your data. This is the precision stage.

## 7. Metrics to report (these go in the paper, not "100% val acc")

* Overall accuracy AND per-class **precision, recall, F1**.
* **Confusion matrix** (shows what gets confused with what).
* **ROC / PR curve** and the operating threshold you chose.
* **False alarms per hour** on the held-out continuous background recording.
  This is the number reviewers and deployers care about most.
* **Detection vs distance** (recall at 3/5/10/15/20 m) - your pole story.
* Stage-1 alone, Stage-2 alone, and the **two-stage combined** numbers.

Report all of these on the **held-out test set / real recordings**, and state
the dataset size and composition. Never report the synthetic bootstrap numbers
as detection performance.

## 8. Export and deploy

`ml/train_gpu.py` writes:
* `ml/out/stage1_int8.tflite` and `stage1_model_data.cc` (for the ESP32 TFLM
  build, `-DUSE_TFLM_STAGE1`).
* `ml/out/stage1_metrics.json` (the numbers for the paper).

Verify **feature parity** before flashing: run the same 2 s WAV through
`ml/mfcc.py` (Python) and the node's `computeMFCC` (C) and confirm they match;
otherwise the on-device model sees different features than it trained on. Edge
Impulse is an alternative that guarantees this if the hand match is fiddly.

---

## Running the training (pick one GPU platform)

**Google Colab (free GPU, easiest):** new notebook, Runtime -> GPU, then one cell:
```
!git clone https://github.com/SV-1411/drone.git && cd drone && \
 pip -q install tensorflow librosa soundfile scikit-learn kaggle && \
 python ml/train_gpu.py --epochs 60
```
For the Kaggle scream data, upload your `kaggle.json` first (Files pane) or run
`from google.colab import files; files.upload()` and place it at
`~/.kaggle/kaggle.json`. Then download `ml/out/` when done.

**Kaggle notebook:** enable GPU + Internet, add the scream dataset as an input,
`!git clone ... && python ml/train_gpu.py`.

**Lightning AI / any GPU box:** in the terminal:
```
git clone https://github.com/SV-1411/drone.git && cd drone
pip install tensorflow librosa soundfile scikit-learn kaggle
python ml/train_gpu.py --epochs 60
git add ml/out/stage1_int8.tflite ml/out/stage1_metrics.json && git commit -m "trained model" && git push
```

After training, commit `ml/out/stage1_int8.tflite` and `stage1_metrics.json`
back to the repo (and copy the `.cc` into `firmware/node/` for the TFLM build).
Then put the metrics from `stage1_metrics.json` into the paper's results table.
