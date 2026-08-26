# Phase-2 distress classifier dataset

Place WAV clips in:

```text
dataset/
├── distress/       # genuine distress vocalizations: screams, cries, wails, calls for help
├── normal/         # normal human speech, laughter, singing, ordinary shouting
└── noise/          # sirens, alarms, horns, engines, music, animals, weather, synthetic/fake noises
```

The training script treats **one recording as one example**. Do not split windows from the same source recording across train/test manually; this prevents leakage.

Recommended first-pass target:

- 50–100 distress clips
- 50–100 normal-human clips
- 100+ noise/hard-negative clips

For a minimum smoke training run, provide at least 2 clips per class. For meaningful evaluation, use substantially more and keep separate recordings for validation/testing.

Supported input for the training script is PCM WAV (8-bit or 16-bit, mono or multi-channel). Other formats should be converted to WAV before training.
