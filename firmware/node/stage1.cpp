/*
 * Stage-1 classifier implementation. See stage1.h.
 *
 * MFCC constants MUST match ml/mfcc.py:
 *   SR 16000, window 2.0 s (32000 samples), n_fft 512, hop 256,
 *   40 mel filters 0..8000 Hz, 13 MFCC (DCT-II), pre-emphasis 0.97,
 *   Hamming window, log(mel + 1e-6). frames = 1 + (32000-512)/256 = 123.
 *
 * The TFLM branch (USE_TFLM_STAGE1) expects a TensorFlow Lite Micro library.
 * Tested option: the Arduino library "Chirale_TensorFlowLite" (ESP32) or
 * Espressif's "esp-tflite-micro". Copy ml/out/stage1_model_data.cc into this
 * folder as model_data.cc so g_stage1_model_data / _len are linked in.
 *
 * NOTE: this file has not been compiled on hardware in this repo. Build it in
 * Arduino/PlatformIO for the ESP32-S3, confirm the MFCC matches ml/mfcc.py on
 * a shared test clip, then flash. Edge Impulse is an alternative that generates
 * the whole front-end + model with guaranteed feature parity if you prefer.
 */
#include "stage1.h"
#include <math.h>
#include <string.h>

static const int   SR = 16000;
static const int   N_SAMPLES = 32000;
static const int   N_FFT = 512;
static const int   HOP = 256;
static const int   N_MELS = 40;
static const int   N_MFCC = 13;
static const int   N_FRAMES = 1 + (N_SAMPLES - N_FFT) / HOP;   // 123
static const float PREEMPH = 0.97f;
static const float EPS = 1e-6f;

// ---------------- MFCC front-end (mirrors ml/mfcc.py) ----------------------
static float hamming_[N_FFT];
static float melFb_[N_MELS][N_FFT / 2 + 1];
static float dct_[N_MFCC][N_MELS];
static bool  tablesReady = false;

static float hzToMel(float f) { return 2595.0f * log10f(1.0f + f / 700.0f); }
static float melToHz(float m) { return 700.0f * (powf(10.0f, m / 2595.0f) - 1.0f); }

static void buildTables() {
  for (int n = 0; n < N_FFT; n++)
    hamming_[n] = 0.54f - 0.46f * cosf(2.0f * (float)M_PI * n / (N_FFT - 1));
  const int nBins = N_FFT / 2 + 1;
  float melMin = hzToMel(0.0f), melMax = hzToMel(SR / 2.0f);
  int binPts[N_MELS + 2];
  for (int i = 0; i < N_MELS + 2; i++) {
    float mel = melMin + (melMax - melMin) * i / (N_MELS + 1);
    binPts[i] = (int)floorf((N_FFT + 1) * melToHz(mel) / SR);
  }
  memset(melFb_, 0, sizeof(melFb_));
  for (int m = 1; m <= N_MELS; m++) {
    int l = binPts[m - 1], c = binPts[m], r = binPts[m + 1];
    for (int k = l; k < c && k < nBins; k++) if (c > l) melFb_[m - 1][k] = (float)(k - l) / (c - l);
    for (int k = c; k < r && k < nBins; k++) if (r > c) melFb_[m - 1][k] = (float)(r - k) / (r - c);
  }
  for (int i = 0; i < N_MFCC; i++)
    for (int j = 0; j < N_MELS; j++)
      dct_[i][j] = cosf((float)M_PI * i * (2 * j + 1) / (2 * N_MELS));
  tablesReady = true;
}

// In-place iterative radix-2 FFT (real input packed into complex).
static void fft(float* re, float* im, int n) {
  for (int i = 1, j = 0; i < n; i++) {
    int bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (int len = 2; len <= n; len <<= 1) {
    float ang = -2.0f * (float)M_PI / len;
    float wr = cosf(ang), wi = sinf(ang);
    for (int i = 0; i < n; i += len) {
      float cwr = 1.0f, cwi = 0.0f;
      for (int k = 0; k < len / 2; k++) {
        float ur = re[i + k], ui = im[i + k];
        float vr = re[i + k + len / 2] * cwr - im[i + k + len / 2] * cwi;
        float vi = re[i + k + len / 2] * cwi + im[i + k + len / 2] * cwr;
        re[i + k] = ur + vr; im[i + k] = ui + vi;
        re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
        float nwr = cwr * wr - cwi * wi; cwi = cwr * wi + cwi * wr; cwr = nwr;
      }
    }
  }
}

// Writes N_FRAMES*N_MFCC features (row-major, frame-major) into out.
static void computeMFCC(const int16_t* audio, int samples, float* out) {
  if (!tablesReady) buildTables();
  static float x[N_SAMPLES];
  for (int i = 0; i < N_SAMPLES; i++) x[i] = (i < samples) ? audio[i] / 32768.0f : 0.0f;
  for (int i = N_SAMPLES - 1; i > 0; i--) x[i] = x[i] - PREEMPH * x[i - 1];  // pre-emphasis
  static float re[N_FFT], im[N_FFT], power[N_FFT / 2 + 1], mel[N_MELS];
  for (int f = 0; f < N_FRAMES; f++) {
    for (int n = 0; n < N_FFT; n++) { re[n] = x[f * HOP + n] * hamming_[n]; im[n] = 0.0f; }
    fft(re, im, N_FFT);
    for (int k = 0; k <= N_FFT / 2; k++) power[k] = re[k] * re[k] + im[k] * im[k];
    for (int m = 0; m < N_MELS; m++) {
      float e = 0.0f;
      for (int k = 0; k <= N_FFT / 2; k++) e += melFb_[m][k] * power[k];
      mel[m] = logf(e + EPS);
    }
    for (int i = 0; i < N_MFCC; i++) {
      float c = 0.0f;
      for (int m = 0; m < N_MELS; m++) c += dct_[i][m] * mel[m];
      out[f * N_MFCC + i] = c;
    }
  }
}

// ---------------- classifier backends --------------------------------------
#ifdef USE_TFLM_STAGE1
#include <TensorFlowLite.h>
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"

extern const unsigned char g_stage1_model_data[];
extern const int g_stage1_model_data_len;

namespace {
  constexpr int kArena = 40 * 1024;                 // tune to the model
  alignas(16) uint8_t tensorArena[kArena];
  const tflite::Model* model = nullptr;
  tflite::MicroInterpreter* interp = nullptr;
}

void stage1_init() {
  buildTables();
  model = tflite::GetModel(g_stage1_model_data);
  static tflite::MicroMutableOpResolver<8> resolver;
  resolver.AddConv2D(); resolver.AddFullyConnected(); resolver.AddRelu();
  resolver.AddSoftmax(); resolver.AddReshape(); resolver.AddMean();
  resolver.AddQuantize(); resolver.AddDequantize();
  static tflite::MicroInterpreter si(model, resolver, tensorArena, kArena);
  interp = &si;
  interp->AllocateTensors();
}

Stage1Result stage1_infer(const int16_t* audio, int samples) {
  static float feat[N_FRAMES * N_MFCC];
  computeMFCC(audio, samples, feat);
  TfLiteTensor* in = interp->input(0);
  float s = in->params.scale; int zp = in->params.zero_point;
  for (int i = 0; i < N_FRAMES * N_MFCC; i++) {
    int q = (int)lroundf(feat[i] / s) + zp;
    in->data.int8[i] = (int8_t)(q < -128 ? -128 : (q > 127 ? 127 : q));
  }
  interp->Invoke();
  TfLiteTensor* out = interp->output(0);
  float os = out->params.scale; int oz = out->params.zero_point;
  int best = 0; float bestp = -1e9f;
  for (int c = 0; c < 4; c++) {
    float p = (out->data.int8[c] - oz) * os;
    if (p > bestp) { bestp = p; best = c; }
  }
  return { best, bestp };
}

#else   // -------- heuristic fallback (no model needed) --------------------
void stage1_init() { buildTables(); }

Stage1Result stage1_infer(const int16_t* audio, int samples) {
  double energy = 0, hi = 0; int16_t prev = 0;
  for (int i = 0; i < samples; i++) {
    energy += (double)audio[i] * audio[i];
    double d = (double)audio[i] - prev; hi += d * d; prev = audio[i];
  }
  float rms = sqrtf(energy / samples) / 32768.0f;
  float band = energy > 0 ? (float)(hi / (4.0 * energy)) : 0.0f;
  float score = 0.6f * fminf(1.0f, rms / 0.08f) + 0.4f * fminf(1.0f, band);
  // heuristic cannot tell scream from help; report scream if it fires
  return { score >= 0.60f ? S1_SCREAM : S1_BACKGROUND, score };
}
#endif
