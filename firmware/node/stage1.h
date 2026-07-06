/*
 * Stage-1 distress classifier interface for the ESP32-S3 node.
 *
 * Two builds, chosen at compile time:
 *   default            heuristic (loud + high-band burst), always compiles,
 *                      used for pipeline bring-up before the model exists.
 *   -DUSE_TFLM_STAGE1  real MFCC + TensorFlow Lite Micro CNN. Requires the
 *                      exported model (ml/out/stage1_model_data.cc copied in
 *                      as model_data.cc) and a TFLM library (see the .cpp).
 *
 * The MFCC in stage1.cpp mirrors ml/mfcc.py step for step so the features on
 * the node match the features the model trained on. If you change one, change
 * both and re-check tests/test_mfcc.py.
 */
#pragma once
#include <stdint.h>

// Class indices match ml/train_stage1.py CLASSES = [background, scream, cry, help]
// and the node event codes (background=0 -> no alert; 1 scream, 2 help, 3 cry).
enum Stage1Class { S1_BACKGROUND = 0, S1_SCREAM = 1, S1_CRY = 2, S1_HELP = 3 };

struct Stage1Result {
  int   cls;          // argmax class index
  float confidence;   // probability of that class, 0..1
};

// Call once in setup().
void stage1_init();

// Classify one 2 s window of 16 kHz mono int16 audio (samples = 32000).
Stage1Result stage1_infer(const int16_t* audio, int samples);

// Maps a Stage1Class to the wire event code used in the LoRa packet.
inline uint8_t stage1_event_code(int cls) {
  switch (cls) {
    case S1_SCREAM: return 1;
    case S1_HELP:   return 2;
    case S1_CRY:    return 3;
    default:        return 0;   // background: no alert
  }
}
