# VanniKawachh: Muffled Voice Distress Dataset & Model Training Specification

This document is the authoritative engineering and training guide for developing, training, evaluating, and deploying the **Muffled Audio Distress Classification Model** for the VanniKawachh acoustic intelligence network. Any AI coding agent or ML engineer reading this document must follow the architectural contracts and guidelines detailed below without deviating or hallucinating non-existent APIs.

---

## 1. Project Context & Architectural Foundation

**VanniKawachh** is a distributed acoustic intelligence and autonomous drone response network designed for women safety:
1. **Stage 1 (Sensing Nodes - ESP32-S3 + INMP441)**: On-device MFCC extraction + quantized int8 CNN running locally on pole-mounted nodes. Detects potential distress bursts and sends AES-128 sealed LoRa packets.
2. **Stage 2 (Hub Service - Raspberry Pi 5 / Cloud Render API)**: Receives alerts and 4-second audio clips. Evaluates clips via audio feature extractors, YAMNet/PANNs, keyword recognition (`bachao`, `help`), vocal prosody, and the additive voice distress decision engine (`hub/voice_decision.py`).
3. **Response Layer (Autonomous Drone Flight Stack)**: Dispatches an autonomous quadcopter to surveyed GPS coordinates upon verified acoustic distress confirmation.

---

## 2. Current Model Training Status (As of September 2026)

| Model / Subsystem | Path / File | Status | Technical Details |
| :--- | :--- | :--- | :--- |
| **Stage 1 Microcontroller Model** | `ml/out/stage1_int8.tflite` | **Trained** | 8-bit quantized TFLite model using 40-band MFCCs for ESP32-S3. |
| **Stage 2 Hub SVM Classifier** | `hub/models/distress_svm.pkl`<br>`hub/models/yamnet.tflite` | **Trained** | SVM classifier on top of YAMNet embeddings + acoustic features trained on ASVP-ESD dataset (97.25% internal accuracy on speaker holdout seed 42). |
| **Keyword & Prosody Engine** | `hub/spoken_stress.py`<br>`hub/distress_keywords.py` | **Active (DSP/ASR)** | ASR for emergency words (`bachao`, `help`) with $F_0$ pitch elevation / prosodic analysis. |
| **Voice Distress 5-Class Model** | `hub/models/voice_distress.tflite` | **NOT TRAINED** | Architecture and trainer exist in `ml/train_voice_distress.py`, but the model artifact **does not exist yet** in `hub/models/`. |
| **Muffled Distress Audio Support** | `hub/voice_decision.py`<br>`ml/train_voice_distress.py` | **NOT TRAINED** | Only diagnostic DSP checks (`high/low < 0.045`) and training augmentations exist; no model has been trained on muffled distress data. |

---

## 3. Acoustic Physics of Muffled Distress Audio

Muffled distress audio occurs when a victim's mouth is occluded (e.g., covered by a cloth, scarf, garment, gag, or hand). 

### Acoustic Characteristics:
1. **High-Frequency Spectral Roll-off**: Fabrics and soft tissues act as acoustic low-pass filters. Frequencies above **1.2 kHz – 1.8 kHz** suffer severe attenuation (20 dB to 40 dB reduction).
2. **Formant Damping**: Vocal tract resonances and high formants ($F_2, F_3, F_4$) are blurred, causing phonetic degradation (standard ASR/STT engines fail).
3. **Preserved Fundamental Frequency ($F_0$)**: Vocal cord vibrations (pitch base $F_0$, typically 150 Hz – 500 Hz for strained voices/screams) conduct through tissue and porous cloth, preserving fundamental harmonics.
4. **Reduced Radiated Acoustic Power**: Overall RMS power drops substantially, creating low Signal-to-Noise Ratio (SNR) at distant microphones.

---

## 4. Dataset Sourcing Strategy

Because public corpora of real-world emergencies with cloth-gagged victims are unavailable due to ethics and safety, training must use a **three-pillar dataset strategy**:

### Pillar A: Base Distress Audio & Hard Negatives (Public Corpora)
1. **ASVP-ESD (Primary Vocal Distress)**:
   - **Download**: [Zenodo Record 7132783](https://zenodo.org/records/7132783) / [Zenodo Record 4782712](https://zenodo.org/records/4782712)
   - **Content**: Non-scripted screams, panic, cries, groans, sadness, fear (16 kHz mono WAV).
   - **Hard Negatives**: Use laughter, normal talking, neutral voices from ASVP-ESD.
2. **AudioSet (Google / YouTube Ontology)**:
   - **Download**: [AudioSet Ontology](https://research.google.com/audioset/ontology/index.html)
   - **Classes**: `Screaming` (`/m/03qc9zr`), `Crying, sobbing` (`/m/07qz6j`), `Groan` (`/m/07s12c4`), `Wail, moan` (`/m/07sr15c`).
3. **FSD50K (Environmental Hard Negatives)**:
   - **Download**: [Zenodo Record 4060432](https://zenodo.org/records/4060432)
   - **Content**: Traffic, sirens, car horns, dog barks, music, wind, construction noise.
4. **CREMA-D & RAVDESS (Emotional Speech)**:
   - **CREMA-D**: [GitHub Repository](https://github.com/CheyneyComputerScience/CREMA-D)
   - **RAVDESS**: [Zenodo Record 1188976](https://zenodo.org/records/1188976)
   - **Content**: Strained and emotional speech to prevent false positives on regular emotional talk.

### Pillar B: DSP-Based Acoustic Muffling Augmentation
In `ml/train_voice_distress.py`, augment clean distress clips with:
- **Low-pass filtering**: 2nd–4th order Butterworth filter with random cutoffs between **500 Hz and 1500 Hz**.
- **First-order IIR filtering**: $\alpha \in [0.025, 0.20]$ simulating heavy cloth absorption.
- **Random gain scaling**: $0.35\times$ to $1.25\times$.
- **Background noise mixing**: SNR between $0\text{ dB}$ and $24\text{ dB}$ using chatter and environmental interference.

### Pillar C: Controlled Physical Field Recordings
Record 30–50 consented audio clips in a quiet room:
- **Conditions**: Cotton cloth/scarf over mouth, hand over mouth, screaming/groaning into a pillow/garment.
- **Utterances**: Strained muffled screams, groans of struggle, muffled calls (*"bachao"*, *"help"*, *"chhod do"*).
- **Format**: 16-bit PCM WAV, 16,000 Hz sample rate, mono channel.

---

## 5. Directory Structure & Manifest Schema

### Workspace Layout:
```text
drone/
├── dataset/
│   ├── distress/                # Clear and muffled screams, cries, groans
│   ├── normal/                  # Normal conversation, laughter, neutral speech
│   └── noise/                   # Sirens, traffic, wind, environmental sounds
├── data/
│   └── voice_manifest.csv       # Master training & validation split manifest
├── hub/
│   ├── models/
│   │   ├── voice_distress.tflite          # Target model output
│   │   └── voice_distress_meta.json       # Exported model metadata
│   └── voice_decision.py        # Production inference runtime
└── ml/
    └── train_voice_distress.py  # Model trainer script
```

### `data/voice_manifest.csv` Required Columns:
The manifest **must** contain exactly these 10 header columns:
```csv
path,split,label,speaker_group,source,license,language,environment,condition,sha256
```

#### Valid Column Values:
- **`split`**: `train`, `validation`, or `test`. (Strict rule: A `speaker_group` must never appear in more than one split to prevent data leakage).
- **`label`** (must match one of the 5 canonical classes):
  1. `distressed_speech`
  2. `scream`
  3. `cry_wail`
  4. `ordinary_voice`
  5. `background_interference`
- **`condition`**: `clean`, `muffled`, `whisper`, `cloth_occluded`, `noisy`, `reverb`.

#### Example Manifest Rows:
```csv
path,split,label,speaker_group,source,license,language,environment,condition,sha256
dataset/distress/muffled_scream_01.wav,train,scream,spk01,consented-custom,internal,na,indoor,muffled,a1b2c3...
dataset/distress/cloth_bachao_02.wav,train,distressed_speech,spk02,consented-custom,internal,hi,indoor,cloth_occluded,d4e5f6...
dataset/distress/asvp_scream_03.wav,validation,scream,spk03,ASVP-ESD,Zenodo-4782712,na,indoor,clean,7g8h9i...
dataset/normal/normal_hindi_01.wav,train,ordinary_voice,spk04,CREMA-D,Open,hi,indoor,clean,1j2k3l...
dataset/noise/traffic_01.wav,train,background_interference,env01,FSD50K,CC-BY,na,outdoor,noisy,4m5n6o...
```

---

## 6. Model Architecture & Inference Contract

### Input Specification:
- **Shape**: `[1, 96, 64, 1]` (Batch, Time-Frames, Mel-Bands, Channels)
- **Sample Rate**: 16,000 Hz
- **Frontend**: Log-mel filterbank (512 FFT, 400 window length, 160 hop size, 64 mel bands between 20 Hz and 8,000 Hz, interpolated to 96 time frames).

### Model Architecture (`tf.keras` / TFLite):
```python
model = tf.keras.Sequential([
    tf.keras.layers.Input((96, 64, 1)),
    tf.keras.layers.LayerNormalization(),
    tf.keras.layers.Conv2D(24, 3, padding="same", activation="relu"),
    tf.keras.layers.MaxPool2D(),
    tf.keras.layers.SeparableConv2D(48, 3, padding="same", activation="relu"),
    tf.keras.layers.MaxPool2D(),
    tf.keras.layers.SeparableConv2D(72, 3, padding="same", activation="relu"),
    tf.keras.layers.GlobalAveragePooling2D(),
    tf.keras.layers.Dropout(0.25),
    tf.keras.layers.Dense(5, activation="softmax"),
])
```

### Output Probabilities:
Order of 5 output softmax probabilities:
`[distressed_speech, scream, cry_wail, ordinary_voice, background_interference]`

### Decision Thresholds (`hub/voice_decision.py`):
```text
VOICE_DISTRESS_MODEL=hub/models/voice_distress.tflite
VOICE_STRONG_THRESHOLD=0.90      # Single strong window triggers confirmation
VOICE_MODERATE_THRESHOLD=0.65    # Two consecutive overlapping windows trigger confirmation
VOICE_KEYWORD_THRESHOLD=0.55     # Combined with keyword detection
```

---

## 7. Execution & Training Commands

### Step 1: Install Dependencies (Offline GPU Machine)
```powershell
pip install tensorflow numpy scipy soundfile librosa
```

### Step 2: Run Training & TFLite Quantization
```powershell
python -m ml.train_voice_distress `
  --manifest data/voice_manifest.csv `
  --output hub/models/voice_distress.tflite `
  --epochs 35 `
  --augmentations 3
```

### Step 3: Run Unit & Integration Tests
```powershell
python -m pytest tests/test_voice_decision.py tests/test_hub.py -v
```

---

## 8. Anti-Hallucination Guardrails & Critical Rules

1. **No PyTorch / Heavy Dependencies on Render**: The deployment environment (Render / Raspberry Pi 5) uses lightweight `ai-edge-litert` (or `tflite_runtime`) + NumPy. Never introduce PyTorch, TorchAudio, or heavy frameworks into the inference path in `hub/`.
2. **Never Dispatch on Raw Audio Energy / Volume Alone**: Loud noises, dropped microphones, or door slams must not trigger drone dispatches. Only confirmed model classifications or verified keyword+prosody triggers are dispatch-worthy.
3. **No Speaker Leakage Across Splits**: The training script verifies that speakers in `train` do not appear in `validation` or `test`.
4. **Muffled Audio Quality Tag Is Non-Rejecting**: In `hub/voice_decision.py`, the boolean flag `quality.muffled` is an explanatory audit metric. It must **never** be used as a hard rejection gate against distress signals.
