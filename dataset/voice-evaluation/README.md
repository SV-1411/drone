# Voice-distress evaluation fixtures

This directory is the versioned, evaluation-only record for the real-audio
voice-distress checks performed on 2026-08-31.  It exists so that a future
evaluation can reproduce the exact source bytes, the detector configuration,
and the observed result.

## Contents and scope

`audio/` contains four public-release-authorised source clips.  The repository
owner explicitly confirmed permission to publish them in this public GitHub
repository on 2026-08-31.  Two originated as user-supplied YouTube examples;
two are user-supplied WhatsApp recordings.  The source names are normalised
only for stable paths; `manifest.csv` preserves the original filenames,
provenance, checksums, duration and result.

These files are **evaluation fixtures only**:

- They are not a training, validation, or test split for `ml/train_voice_distress.py`.
- No `voice_distress.tflite` model has been trained from these clips.
- Do not treat the repository owner's publication confirmation as a licence
  for unrelated reuse.  Anyone reusing a clip must independently verify its
  rights and obtain any required consent.

The project already has two small, canonical audio fixtures at
`hub/models/demo_scream.wav` and `ml/testclips/wilhelm.ogg`.  They are tracked
at those original paths to avoid duplicate copies; their checksums are also
recorded in `manifest.csv`.

## Reproducing the recorded run

The clips were normalised to mono, 16 kHz PCM WAV before inference:

```powershell
ffmpeg -i dataset/voice-evaluation/audio/03_people-scream-at-sea.mp3 `
  -ac 1 -ar 16000 -c:a pcm_s16le evaluation.wav
```

The full route was evaluated with the project's live Stage-1 detector,
production fallback `YAMNet (AudioSet fallback)`, temporal confirmation, and
the existing fusion/dispatch decision.  PANN was not installed locally, so
the configured YAMNet fallback was used.  See `manifest.csv` for the exact
Stage-1, Stage-2 and safe dispatch-simulation results.

The test dispatcher was a recording-only stub: no real drone command or
mission was created during evaluation.
