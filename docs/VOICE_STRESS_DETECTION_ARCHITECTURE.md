# Voice Stress Detection: Unified Classifier Architecture

## Problem Statement

The current Stage-1 / Stage-2 pipeline classifies distress based on
**loudness** and **generalised sound-event labels** (YAMNet/PANNs). It cannot
detect a **quiet, stressed human voice** — someone whispering "help me" in fear
at the same amplitude as normal conversation.

| Path | What it detects | Gap |
|------|----------------|-----|
| `scream_dsp.py` (DSP) | Wordless screams | Requires loudness (RMS ≥ 0.05); misses quiet voice |
| YAMNet / PANNs | Generic AudioSet sound classes | No "stressed speech" class; scores drop on quiet audio |
| `spoken_stress.py` | Vocal prosody (F0, centroid, SNR) | Only runs *after* ASR matches an exact emergency keyword |
| Stage-1 NN (on-device) | Cry detection | Only class 2 (cry) fires; no stressed speech class |

**Result**: A person in distress who whispers, speaks softly, or uses words
not in the keyword list goes undetected.

---

## Why Previous Approaches Failed

The original proposal layered three threshold-based fixes on top of each other:

| Approach | Why it fails |
|----------|-------------|
| Make `spoken_stress.py` independent | Still uses fixed Hz thresholds (145 Hz floor) that break across speakers |
| Add adaptive F0 baseline | Still a rule: "30% above baseline = stressed." Breaks on monotone speakers, vocal fry, children |
| Add jitter/HNR to the existing SVM | Bolts three features onto a system built around YAMNet embeddings — doesn't fundamentally change detection |

**Core insight**: Stress detection is a **pattern recognition problem**. The
right tool is a **trained classifier**, not nested if-statements with tunable
thresholds. Every threshold is a decision boundary that will break on an edge
case. A trained model learns the decision boundary from data.

---

## Proposed Solution: Single Unified Voice Stress Classifier

One module. One feature set. One trained model. Replaces both `scream_dsp.py`
and `spoken_stress.py` as the signal-based stress detector.

```
┌──────────────────────────────────────────────────────────────────┐
│                     CURRENT PIPELINE                             │
│                                                                  │
│  Audio Clip                                                      │
│    │                                                             │
│    ├──► YAMNet / PANNs (scream/cry labels)                      │
│    │                                                             │
│    ├──► Trained Stage-1 NN (cry class only)                      │
│    │                                                             │
│    ├──► DSP detector (loud + high-pitch + sustained)             │
│    │                                                             │
│    └──► Spoken stress (F0 + centroid + SNR)                      │
│          [BUT: only after ASR keyword match]                     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

                          │
                          ▼

┌──────────────────────────────────────────────────────────────────┐
│                     PROPOSED PIPELINE                            │
│                                                                  │
│  Audio Clip                                                      │
│    │                                                             │
│    ├──► YAMNet / PANNs (wordless vocalizations: screams, cries) │
│    │    → stays as-is, it is good at what it does                │
│    │                                                             │
│    ├──► Stage-1 NN (on-device cry detection)                     │
│    │    → stays as-is, it is on-device and works                 │
│    │                                                             │
│    └──► Voice Stress Classifier (REPLACES DSP + spoken_stress)   │
│         ── extracts stress-specific acoustic features            │
│         ── trained Random Forest classifier                      │
│         ── outputs: stress_probability (0.0 - 1.0)              │
│         ── threshold: > 0.6 → flag as potential distress         │
│                                                                  │
│  Stage-2 (hub):                                                  │
│    ├──► PANNs / YAMNet (existing)                                │
│    ├──► Voice stress probability (NEW input feature)             │
│    ├──► Acoustic features including jitter + HNR (NEW)           │
│    └──► SVM classifier (retrained) + temporal gate               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## The Right Features: What Actually Correlates With Vocal Stress

These features are drawn from speech pathology and affective computing
research. They measure **vocal physiology under stress**, not just volume.

| Feature | What it measures | Why it matters | Volume-dependent? | Speaker-dependent? |
|---------|-----------------|----------------|-------------------|-------------------|
| **F0 mean** | Average pitch | Stressed voice is elevated | No | Partially (baseline normalised) |
| **F0 std** | Pitch variability | Stressed voice is more variable | No | No (ratio) |
| **F0 range** | Pitch excursion | Stressed voice has wider swings | No | No (ratio) |
| **Jitter (RAP)** | Cycle-to-cycle pitch perturbation | Stressed vocal cords vibrate less steadily | No | No (relative measure) |
| **Jitter (PPQ5)** | 5-point pitch perturbation quotient | Smoother jitter estimate, same principle | No | No |
| **Shimmer (APQ5)** | 5-point amplitude perturbation | Stress causes amplitude instability | No | No (relative measure) |
| **HNR** | Harmonics-to-noise ratio | Stress → incomplete vocal fold closure → more breath noise | No | Partially |
| **F1, F2, F3** | Formant frequencies | Stress shifts vocal tract resonance | No | Yes (normalised per speaker) |
| **Spectral tilt** | High vs low frequency energy rolloff | Stressed voice has more high-frequency energy | No | No (ratio) |
| **Speaking rate** | Syllables per second | Stressed speech is often faster | No | No (relative to speaker) |
| **Pause ratio** | Silence fraction of clip | Stress → fewer/shorter pauses | No | No |
| **MFCCs (13 coeffs)** | General spectral shape | Captures everything the specific features miss | Partially | Partially |

**Why these features beat raw frequency thresholds**: They are mostly
**ratios and perturbation measures**, not absolute values. Jitter doesn't care
if your voice is 100 Hz or 300 Hz — it measures whether the pitch is
*unstable*. HNR doesn't care if you're loud or quiet — it measures whether
the voice is *breathy*. This makes them inherently robust across speakers,
ages, and recording conditions.

---

## Module Design: `hub/voice_stress_classifier.py`

### Responsibilities

1. **Feature extraction**: Compute the 12-15 stress-relevant features from any audio clip
2. **Classification**: Run a trained model to output a stress probability
3. **Nothing else**: No ASR dependency, no loudness gate, no temporal logic

### Public interface

```python
from hub.voice_stress_classifier import VoiceStressClassifier

classifier = VoiceStressClassifier(model_path="hub/models/voice_stress_rf.pkl")

result = classifier.predict(audio_array, sample_rate=16000)

# result.stress_probability  → float 0.0-1.0
# result.is_stressed         → bool (result.stress_probability > threshold)
# result.features            → dict of extracted features (for logging/debugging)
# result.confidence          → string "high" / "medium" / "low"
```

### Internal structure

```
voice_stress_classifier.py
│
├── extract_features(audio, sr) → dict
│   ├── compute_f0(audio, sr) → f0_values
│   ├── compute_jitter(f0_values) → float
│   ├── compute_shimmer(audio, sr, f0_values) → float
│   ├── compute_hnr(audio, sr, f0_values) → float
│   ├── compute_formants(audio, sr) → (f1, f2, f3)
│   ├── compute_spectral_tilt(audio, sr) → float
│   ├── compute_speaking_rate(audio, sr) → float
│   ├── compute_pause_ratio(audio, sr) → float
│   └── compute_mfcc(audio, sr) → 13-dim vector
│
├── VoiceStressClassifier
│   ├── __init__(model_path) → loads sklearn model
│   ├── predict(audio, sr) → StressResult
│   └── _features_to_vector(features) → numpy array
```

### Dependencies

- **NumPy** — already used throughout
- **librosa** (optional) — for F0 extraction, formant estimation. Can fall back to pure NumPy implementations
- **scikit-learn** — for model loading and prediction (lightweight)
- **joblib** — for model serialization

No GPU required. No PyTorch. No TensorFlow. Runs on any hub.

---

## Feature Extraction: How Each Feature Is Computed

### F0 (Fundamental Frequency)

Use autocorrelation-based pitch detection on overlapping frames (25ms window,
10ms hop). This is the same approach already used in `spoken_stress.py` and
`audio_analysis.py`, extended to full-clip analysis.

```python
# Pseudocode
frames = frame_audio(audio, frame_ms=25, hop_ms=10)
f0_values = []
for frame in frames:
    if is_voiced(frame):  # energy > threshold
        f0 = autocorrelation_pitch(frame, sr, fmin=60, fmax=600)
        f0_values.append(f0)
    else:
        f0_values.append(0)  # unvoiced

f0_mean = mean(nonzero(f0_values))
f0_std = std(nonzero(f0_values))
f0_range = max(f0_values) - min(nonzero(f0_values))
```

### Jitter (RAP — Relative Average Perturbation)

Measures cycle-to-cycle pitch instability. Stressed vocal cords produce
irregular vibration.

```python
# For consecutive voiced F0 values
jitter_values = []
for i in range(1, len(f0_voiced)):
    jitter_values.append(abs(f0_voiced[i] - f0_voiced[i-1]) / f0_voiced[i-1])

jitter_rap = mean(jitter_values)

# Normal speech: < 0.01 (1%)
# Stressed speech: > 0.02 (2%)
```

### Shimmer (APQ5 — Amplitude Perturbation Quotient)

Measures cycle-to-cycle amplitude instability, analogous to jitter but for
loudness rather than pitch.

```python
# Extract peak amplitudes of each glottal cycle
peaks = extract_cycle_peaks(audio, f0_values)
apq_values = []
for i in range(2, len(peaks)):
    apq_values.append(
        abs(mean(peaks[i-2:i+3]) - mean(peaks[i-1:i+4])) / mean(peaks[i-2:i+3])
    )
shimmer_apq5 = mean(apq_values)

# Normal: < 0.03
# Stressed: > 0.05
```

### HNR (Harmonics-to-Noise Ratio)

Measures how much of the signal is harmonic (voiced) vs noise (breathiness).
Stress → incomplete vocal fold closure → more breath noise → lower HNR.

```python
# Autocorrelation method
for each voiced frame:
    ac = autocorrelation(frame)
    h_peak = max(ac[lag_min:lag_max])  # harmonic peak
    n_energy = mean(ac) - h_peak       # noise floor
    hnr_frame = 10 * log10(h_peak / n_energy)

hnr = mean(hnr_frames)

# Normal: 15-20 dB
# Stressed: 8-12 dB
```

### Formants (F1, F2, F3)

Vocal tract resonance frequencies. Stress shifts formant positions.

```python
# LPC (Linear Predictive Coding) method
for each voiced frame:
    lpc_coeffs = lpc(frame, order=12)
    roots = polynomial_roots(lpc_coeffs)
    formants = sorted imaginary parts of roots > 50 Hz
    f1, f2, f3 = formants[0], formants[1], formants[2]
```

### Spectral Tilt

Ratio of high-frequency energy to total energy. Stressed voice has more
high-frequency energy due to increased subglottal pressure.

```python
fft = rfft(frame)
freqs = rfftfreq(len(frame), 1/sr)
total_energy = sum(abs(fft)**2)
hf_energy = sum(abs(fft[freqs > 2000])**2)
spectral_tilt = hf_energy / total_energy
```

### Speaking Rate & Pause Ratio

Temporal features of speech delivery.

```python
# Speaking rate: voiced segments per second
voiced_segments = find_voiced_segments(audio, sr)
speaking_rate = len(voiced_segments) / duration(audio)

# Pause ratio: fraction of time in silence
pause_duration = sum(segment durations where energy < threshold)
pause_ratio = pause_duration / duration(audio)

# Stressed: high speaking_rate, low pause_ratio
```

---

## Training Pipeline: `ml/train_voice_stress.py`

### Input data format

```
ml/data/
  stress/
    stressed_clip_001.wav
    stressed_clip_002.wav
    ...
  normal/
    normal_clip_001.wav
    normal_clip_002.wav
    ...
```

Labels are derived from directory names. Each clip should be 2-10 seconds.
Target: 200+ clips per class minimum (400+ total).

### Training script

```python
# ml/train_voice_stress.py

def main():
    # 1. Load all clips
    stress_clips = load_clips("ml/data/stress/")
    normal_clips = load_clips("ml/data/normal/")

    # 2. Extract features from each clip
    X_stress = [extract_features(clip, sr) for clip in stress_clips]
    X_normal = [extract_features(clip, sr) for clip in normal_clips]

    # 3. Build dataset
    X = concatenate(X_stress, X_normal)
    y = [1]*len(X_stress) + [0]*len(X_normal)

    # 4. Train Random Forest
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=15,
        min_samples_leaf=5,
        class_weight="balanced"  # handle class imbalance
    )
    model.fit(X_train, y_train)

    # 5. Evaluate
    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))
    print(f"Feature importances: {dict(zip(FEATURE_NAMES, model.feature_importances_))}")

    # 6. Save
    joblib.dump(model, "hub/models/voice_stress_rf.pkl")
```

### Why Random Forest over alternatives

| Model | Pros | Cons | Verdict |
|-------|------|------|---------|
| **Random Forest** | Fast inference, handles small datasets, interpretable feature importances, no GPU | Less accurate on very large datasets | **Best fit** — 400-2000 clips is the sweet spot |
| SVM | Good with small data, already used in pipeline | Harder to tune kernel, less interpretable | Runner-up |
| Gradient Boosted Trees (XGBoost) | Slightly more accurate than RF | Heavier dependency, more tuning | Overkill for this data size |
| Neural Network (MLP) | Flexible | Needs 5,000+ clips, black box, needs PyTorch/TF | Not now |
| Decision Tree | Interpretable | Overfits on small data | Too simple |

Random Forest is the right choice because:
- It works with the 400-2000 clip range you realistically have
- `feature_importances_` tells you which features actually matter — you can
  prune the feature set and remove features that don't help
- Inference is a single `predict()` call — no GPU, no framework, ~1ms latency
- It's already available via scikit-learn (already in the project)

### Model size and performance

| Metric | Expected |
|--------|----------|
| Model file size | ~500 KB (200 trees, 15 features) |
| Inference time | < 5ms per clip |
| RAM usage | < 50 MB |
| Accuracy (lab data) | 85-92% (acted emotions) |
| Accuracy (real data) | To be measured — likely 75-85% initially |

---

## Integration With the Existing Pipeline

### Stage 1 changes (`hub/webapp.py` — `stage1_phone()`)

```python
# BEFORE: 4 detection paths (YAMNet, NN, DSP, spoken_stress-gated)
# AFTER:  3 detection paths (YAMNet, NN, voice_stress)

def stage1_phone(audio, sr):
    rms = np.sqrt(np.mean(audio**2))

    # Path 1: YAMNet (wordless vocalizations) — unchanged
    yamnet_result = yamnet_detect(audio, sr)
    if yamnet_result.score >= YAMNET_THRESHOLD and rms >= YAMNET_RMS_FLOOR:
        return DetectedAlert(label="scream", score=yamnet_result.score, source="yamnet")

    # Path 2: Stage-1 NN (cry detection) — unchanged
    nn_result = infer_nn(audio)
    if nn_result.class_id == 2 and nn_result.confidence >= NN_THRESHOLD:
        return DetectedAlert(label="cry", score=nn_result.confidence, source="nn")

    # Path 3: Voice Stress Classifier (NEW — replaces DSP + spoken_stress)
    stress_result = voice_stress_classifier.predict(audio, sr)
    if stress_result.is_stressed:
        return DetectedAlert(label="stressed_voice", score=stress_result.stress_probability, source="stress_classifier")

    return DetectedAlert(label="background", score=0, source="none")
```

**What is removed**:
- `scream_dsp.py` call — replaced by voice stress classifier
- `spoken_stress.py` call — replaced by voice stress classifier
- ASR keyword gate — no longer needed for stress detection
- Loudness gate (RMS_FLOOR) — the classifier handles amplitude-independence internally

**What is preserved**:
- YAMNet/PANNs for wordless screams and cries — they are good at that
- Stage-1 NN for on-device cry detection — it works on the microcontroller
- The overall cascade priority (loud screams first, then stress)

### Stage 2 changes (`hub/verifier.py` and `hub/distress_classifier.py`)

The stress probability becomes an additional input feature to the SVM:

```python
# Current feature vector: YAMNet embeddings (521-D) + acoustic features (46-D)
# New feature vector: YAMNet embeddings (521-D) + acoustic features (46-D) + stress_features (15-D) + stress_probability (1-D)

FEATURE_NAMES = [
    # existing 46 features
    "rms_mean", "rms_std", "rms_max", "rms_min",
    "f0_mean", "f0_std", "f0_range", "f0_min", "f0_max",
    "centroid_mean", "centroid_std", "centroid_max",
    "bandwidth_mean", "bandwidth_std",
    "flatness_mean", "flatness_std",
    "rolloff_mean", "rolloff_std",
    "zcr_mean", "zcr_std",
    "energy_low", "energy_mid", "energy_high", "energy_ratio_lh", "energy_ratio_mh",
    "spectral_entropy", "temporal_entropy",
    "silence_ratio", "voiced_ratio", "speech_rate",
    "peak_freq", "harmonic_ratio", "inharmonicity",
    "dynamic_range", "crest_factor", "peak_to_rms",
    "mfcc_1" through "mfcc_13",
    # NEW stress features
    "jitter_rap", "jitter_ppq5", "shimmer_apq5", "hnr",
    "f1_mean", "f2_mean", "f3_mean",
    "spectral_tilt", "speaking_rate", "pause_ratio",
    # NEW stress classifier output
    "stress_probability",
]
```

The SVM is retrained with the expanded feature set:
```bash
python -m hub.train_full_distress_model --dataset dataset --output hub/models
```

### Files to modify

| File | Change | Effort |
|------|--------|--------|
| `hub/voice_stress_classifier.py` | **New file** — feature extraction + classifier inference | ~200 lines |
| `ml/train_voice_stress.py` | **New file** — training script | ~100 lines |
| `ml/data/stress/` | **New directory** — stressed voice clips | Data collection |
| `ml/data/normal/` | **New directory** — normal voice clips (may already exist) | Data collection |
| `hub/webapp.py` (`stage1_phone()`) | Replace DSP + spoken_stress calls with voice stress classifier | ~20 lines changed |
| `hub/audio_features.py` | Add jitter, shimmer, HNR, formant extraction functions | ~80 lines added |
| `hub/distress_classifier.py` | Update FEATURE_NAMES to include new features | ~20 lines changed |
| `hub/train_full_distress_model.py` | Retrain with expanded feature set | ~10 lines changed |
| `hub/models/voice_stress_rf.pkl` | **New file** — trained Random Forest model | Generated by training |
| `scream_dsp.py` | **Deprecated** — no longer called from pipeline | Can be removed |
| `hub/spoken_stress.py` | **Deprecated** — no longer called from pipeline | Can be removed |

---

## Why This Is Better Than Every Other Approach

| Alternative | Why it loses to a trained classifier |
|-------------|--------------------------------------|
| **Adaptive F0 baseline** (rule-based) | "30% above baseline = stressed" is a single linear boundary. Real stress sits in a multi-dimensional feature space (pitch + jitter + HNR + formants + timing). No single rule captures that. |
| **More YAMNet classes** | YAMNet has no "stressed speech" class and you cannot add classes to a frozen model. Fine-tuning YAMNet on stress data is possible but you'd be fighting its architecture (event detection, not state detection). |
| **Bigger Stage-1 NN** | The ESP32 cannot run prosody analysis. MFCC compression destroys the frequency detail needed for jitter/HNR. Firmware changes are high-risk. |
| **Larger PANNs fine-tune** | PANNs classifies sound *events* (scream, cry, siren), not vocal *states* (stressed, calm, fatigued). It is the wrong architecture for this problem. |
| **Threshold tuning on DSP** | You have already tried this. Every fix for one edge case breaks another. Thresholds are brittle because stress is multi-dimensional. |
| **Transformer model (AST/Whisper)** | 87M+ parameters. Needs GPU. Massive overkill for a 15-feature classification problem. |
| **3-layer threshold patchwork** | Still rule-based. Still breaks on new speakers. Still needs manual tuning for every new environment. |

**The trained classifier wins** because:
1. It learns the **decision boundary** from data instead of you hand-coding it
2. It uses **12-15 features simultaneously** — no single rule needs to capture everything
3. It **generalises** to new speakers because the features are mostly speaker-normalised (ratios, perturbations)
4. It is **retrainable** — collect better data, retrain, get better results. No code changes needed.
5. It is **fast** — 5ms inference, no GPU, fits in the existing hub architecture

---

## Training Data: What You Have vs What You Need

### What you have

| Dataset | Clips | Type | Useful for |
|---------|-------|------|-----------|
| ASVP-ESD | ~250 | Acted fear/scream/panic/cry | Partial — acted, not real stress |
| CREMA-D | ~250 | Acted anger/disgust/fear/happy/neutral/sad | Partial — acted emotions |
| ESC-50 | ~300 | Environmental sounds | Background class |
| PANNs fine-tune data | ~1,700 | Mixed AudioSet clips | Sound events, not vocal states |

### What you need

| Category | Clips needed | Why |
|----------|-------------|-----|
| Stressed speech (quiet) | 100+ | Whispered/soft emergency calls — the primary gap |
| Stressed speech (loud) | 50+ | Screams/shouts at various distances |
| Normal conversation | 100+ | Hard negatives — someone talking loudly but not stressed |
| Children's voices | 50+ | Children have higher F0 baselines — model must handle this |
| Multiple languages | 50+ per language | Hindi, English, Hinglish at minimum |
| Various environments | 50+ | Indoors, outdoors, traffic, quiet |

**Minimum viable**: 400 total clips (200 stressed + 200 normal) with the
features described above. This gives the Random Forest enough to learn
meaningful patterns.

**How to collect**: Record yourself and others in controlled stress scenarios
(actor exercises work) and real emergency-like situations (roleplay). The key
requirement is **variety in volume** — some stressed clips should be at
whisper level, some at conversation level, some at shout level.

---

## Implementation Roadmap

### Phase 1: Foundation (1-2 days)

| Step | Task | File |
|------|------|------|
| 1.1 | Write feature extraction functions | `hub/audio_features.py` |
| 1.2 | Write the classifier module | `hub/voice_stress_classifier.py` |
| 1.3 | Write the training script | `ml/train_voice_stress.py` |
| 1.4 | Train on existing data (ASVP-ESD + CREMA-D) as a baseline | Run training script |

### Phase 2: Integration (1 day)

| Step | Task | File |
|------|------|------|
| 2.1 | Replace DSP + spoken_stress calls in stage1_phone() | `hub/webapp.py` |
| 2.2 | Add stress features to the SVM feature set | `hub/audio_features.py`, `hub/distress_classifier.py` |
| 2.3 | Retrain the SVM with expanded features | `hub/train_full_distress_model.py` |

### Phase 3: Data collection (ongoing)

| Step | Task | File |
|------|------|------|
| 3.1 | Collect stressed speech clips at various volumes | `ml/data/stress/` |
| 3.2 | Collect normal speech hard negatives | `ml/data/normal/` |
| 3.3 | Retrain voice stress classifier with better data | Run training script |

### Phase 4: Validation (1 day)

| Step | Task | File |
|------|------|------|
| 4.1 | Unit test each feature extractor with known clips | New test file |
| 4.2 | Integration test full pipeline with stress/non-stress clips | Manual testing |
| 4.3 | Measure accuracy on held-out data | Metrics report |

---

## Testing Strategy

### Unit tests

| Test | Input | Expected |
|------|-------|----------|
| F0 extraction | Clean 440 Hz sine wave | f0_mean ≈ 440, f0_std ≈ 0 |
| Jitter | Steady synthetic voice | jitter < 0.01 |
| Jitter | Unstable synthetic voice | jitter > 0.03 |
| HNR | Clean harmonic signal | hnr > 20 dB |
| HNR | Noisy signal | hnr < 10 dB |
| Feature extraction | Silence clip | All features = 0 or undefined, no crash |

### Integration tests

| Test | Input | Expected |
|------|-------|----------|
| Whispered stressed voice | Soft "help me" clip, RMS ~0.003 | stress_probability > 0.6 |
| Normal conversation | "How are you doing" at normal volume | stress_probability < 0.3 |
| Loud non-stressed | Someone talking loudly, not stressed | stress_probability < 0.4 |
| Child normal voice | Child talking normally | stress_probability < 0.3 |
| Stressed child | Child crying/whispering fearfully | stress_probability > 0.6 |
| Ambient noise only | Traffic, rain, music | stress_probability < 0.2 |

### Regression tests

| Test | Expected |
|------|----------|
| Existing YAMNet scream detection | Still fires on loud screams (unchanged path) |
| Existing NN cry detection | Still fires on detected cries (unchanged path) |
| Background audio | All paths reject (no false positives) |

---

## Summary

| Aspect | Design |
|--------|--------|
| **Architecture** | Single trained classifier (Random Forest) replacing threshold-based DSP + gated spoken stress |
| **Features** | 15 stress-relevant features: F0 stats, jitter, shimmer, HNR, formants, spectral tilt, speaking rate, pause ratio, MFCCs |
| **Volume independence** | Features are ratios and perturbation measures, not absolute values |
| **Speaker robustness** | Features are mostly speaker-normalised; no per-speaker calibration needed |
| **New files** | `hub/voice_stress_classifier.py`, `ml/train_voice_stress.py` |
| **Modified files** | `hub/webapp.py`, `hub/audio_features.py`, `hub/distress_classifier.py` |
| **Removed files** | `scream_dsp.py`, `hub/spoken_stress.py` (deprecated) |
| **Model size** | ~500 KB, no GPU, < 5ms inference |
| **Training data needed** | 400+ clips minimum (200 stressed + 200 normal) |
| **Effort** | 3-5 days for Phase 1-2; Phase 3 is ongoing data collection |
