# Render Voice-Distress Model

This is an additive, recall-first detector for short stress calls, long quiet
distress speech, screams, cries, wails, muffled recordings, and whispers.  It
does not replace PANNs on a future Pi 5 and it does not make a raw loudness,
F0, or SNR measurement dispatch a drone.

## Runtime contract

`hub/voice_decision.py` loads `hub/models/voice_distress.tflite` when present.
Render needs only `ai-edge-litert` and NumPy.  If the model is absent, the new
`/voice-window` endpoint remains diagnostic-only and the existing YAMNet/DSP
and stressed-keyword routes keep their current behaviour.

The model accepts a `[1, 96, 64, 1]` 16 kHz log-mel tensor and emits, in order:

1. `distressed_speech`
2. `scream`
3. `cry_wail`
4. `ordinary_voice`
5. `background_interference`

One calibrated strong event, or two calibrated moderate overlapping windows,
is confirmation.  The thresholds are environment variables only after they
are selected on a held-out validation set:

```text
VOICE_DISTRESS_MODEL=hub/models/voice_distress.tflite
VOICE_STRONG_THRESHOLD=0.90
VOICE_MODERATE_THRESHOLD=0.65
VOICE_KEYWORD_THRESHOLD=0.55
```

Do not lower these from a single demo.  Produce an evaluation report first.

## Data manifest

Training requires a reviewed CSV with exactly these required columns:

```csv
path,split,label,speaker_group,source,license,language,environment,condition,sha256
clips/s01_bachao_whisper.wav,train,distressed_speech,s01,consented-field,consent-v1,hi-en,outdoor,whisper+muffled,<sha256>
clips/s02_scream.wav,validation,scream,s02,ASVP-ESD,Zenodo-4782712,na,indoor,clean,<sha256>
```

`split` is `train`, `validation`, or `test`. `speaker_group` may never appear
in more than one split.  Use `ordinary_voice` for normal, angry, excited,
laughing, and singing voices; use `background_interference` for traffic,
horns, sirens, music, animals, and baby cries.  Keep source URLs/terms and
consent records outside Git, but keep their stable identifiers and checksums in
the manifest.

Official candidate sources include [ASVP-ESD](https://zenodo.org/records/4782712)
and [AudioSet](https://research.google.com/audioset/). AudioSet examples are
weakly labelled YouTube segments: manually review them and do not scrape or
redistribute arbitrary public-web audio.

## Offline training and deployment

On a GPU-capable machine, in an environment with TensorFlow installed:

```bash
python -m ml.train_voice_distress --manifest data/voice_manifest.csv --epochs 35
python -m pytest tests/test_voice_decision.py tests/test_phone_mode.py -q
```

The command writes the TFLite artifact and adjacent metadata. Run the untouched
test split, a separate continuous-background test, and condition slices for
whisper, muffled, quiet/distant speech, short scream, cry/wail, Hindi/Hinglish,
and ordinary excited speech before committing the artifact or enabling
`VOICE_DISTRESS_MODEL`.

`/voice-window` returns model probabilities, quality tags, the event
aggregation path, model version, and dispatch outcome. Quality tags are for
auditing only: a `whisper_like` or `muffled` result must not reject a valid
trained-model detection.
