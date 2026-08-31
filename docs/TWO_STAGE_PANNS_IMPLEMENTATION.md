# Two-Stage Distress Pipeline Implementation

## Target

- **Stage 1:** the complete current distress pipeline runs on the sensing node.
- **Stage 2:** the trained PANNs module runs on the Drone Raspberry Pi 5.
- Stage 1 triggers Stage 2 only for a potential distress event.
- Stage 2 verifies the event; it does not replace Stage 1.

## What is implemented in this branch

### Raspberry Pi 5 / Stage 2

- `hub/verifier.py` now treats PANNs as the Stage-2 verifier rather than the
  previous SVM/YAMNet verification path.
- On the cloud demo service only, the committed YAMNet TFLite model is the
  learned Stage-2 fallback when the Pi-only PANN checkpoint/runtime is absent.
  The energy heuristic never confirms or dispatches an alert.
- Stage-2 inference uses overlapping 1-second windows and requires the configured
  number of positive windows before confirming distress.
- Added PANNs runtime configuration to `hub/config.py`.
- Added `panns-inference` and `torch` to the Python runtime requirements.
- `hub/pipeline.py` now reports the Stage-2 backend as PANNs rather than logging
  the old SVM terminology.

## Raspberry Pi configuration

Set these environment variables before starting the hub:

```text
PANN_CHECKPOINT_PATH=/absolute/path/to/the/trained/panns/checkpoint
PANN_DEVICE=cpu
VERIFY_THRESHOLD=0.70
MIN_DISTRESS_FRAMES=3
```

For the cloud YAMNet fallback, configure independently if needed:

```text
YAMNET_VERIFY_THRESHOLD=0.30
YAMNET_MIN_DISTRESS_FRAMES=3
```

The trained checkpoint is intentionally **not committed** to Git. It must be
placed on the Raspberry Pi 5 and referenced by `PANNS_CHECKPOINT`.

## Important model compatibility requirement

The existing trained PANNs artifact must be compatible with the
`panns-inference` `AudioTagging` architecture used by the adapter. If the
~1,700-audio model was trained using a custom PANNs architecture or a custom
output head, its original model definition and checkpoint-loading code must be
used instead of assuming the stock AudioSet `AudioTagging` interface.

Do not silently substitute a generic pretrained AudioSet model for the trained
project model.

## Stage-1 blocker that must be resolved before claiming full deployment

The repository's current ESP32-S3 sensing firmware still contains a
`MFCC + tiny CNN (TFLM)` Stage-1 implementation. The repository also contains a
Python SVM/acoustic feature pipeline under `hub/`, but that SVM artifact consumes
a YAMNet representation as part of its feature vector. Therefore it cannot be
moved to the ESP32 by simply copying `distress_svm.pkl`.

A faithful implementation of the requested architecture requires the exact
current Stage-1 model/artifacts to be made deployable on the sensing node,
including feature parity and a supported embedded inference representation.
Do not claim that this branch has completed that hardware port until that
requirement is verified on the target sensing-node hardware.

## Required next implementation phase

1. Identify the exact Stage-1 pipeline intended by the current project build.
2. Identify the trained Stage-1 model and all preprocessing/scaler artifacts.
3. Verify whether the Stage-1 classifier can run on the ESP32-S3 without a
   YAMNet dependency. If not, retrain/export a node-compatible representation
   using the same labelled data and validated feature contract.
4. Port the complete Stage-1 feature pipeline to the sensing node with numerical
   parity against the reference implementation.
5. Keep the existing 2-second inference window and event-triggered clip capture
   only if they match the validated Stage-1 specification.
6. Connect the Stage-1 event to the existing WiFi clip upload path.
7. Verify the uploaded clip is exactly what the Raspberry Pi PANNs adapter expects.
8. Run Stage-1 regression tests.
9. Run PANNs standalone tests on the Raspberry Pi.
10. Run end-to-end tests: sensing node -> Stage 1 -> clip/event -> Pi 5 -> PANNs
    -> final decision.
11. Benchmark the complete two-stage system on held-out data before tuning or
    claiming final thresholds.

## Decision boundary

```text
SENSING NODE

Audio
  -> complete Stage 1
  -> potential distress
  -> event + relevant audio

================ NETWORK BOUNDARY ================

DRONE RASPBERRY PI 5

Event/audio
  -> trained PANNs
  -> PANNs distress score
  -> temporal verification
  -> final decision/fusion
```

## Non-negotiable rules

- Do not replace Stage 1 with PANNs.
- Do not remove the current Stage-1 pipeline during integration.
- Do not use the generic pretrained PANNs weights as a substitute for the
  project's trained checkpoint.
- Do not invent the trained checkpoint path.
- Do not invent PANNs output classes; inspect the checkpoint/model metadata.
- Do not change thresholds based on one demo clip.
- Do not merge Stage 1 and Stage 2 into one opaque classifier.
- Do not declare hardware completion until the Stage-1 implementation is
  actually runnable on the sensing node.
