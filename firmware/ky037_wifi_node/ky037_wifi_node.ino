/*
 * VanniKawachh Wi-Fi bench prototype: ESP32-S3 + KY-037.
 *
 * KY-037 AO -> GPIO4, DO -> GPIO5, VCC -> 3V3, GND -> GND.
 * A loudness gate captures two seconds of analogue audio, then the repository's
 * MFCC + trained Stage-1 MLP classifies background/scream/cry/help. The model
 * does not perform speech-to-text or guarantee recognition of the word Bachao.
 * The Pi receiver is deliberately locked against flight dispatch.
 *
 * On USB serial at 115200, provision once with:
 *   WIFI <SSID>|<password>
 *   NODE <node_id>|<latitude>|<longitude>
 *   KEY <64 lowercase or uppercase hex characters>
 *   HOST <Pi IPv4 address>
 *   STATUS
 * Settings survive power cycles in ESP32 NVS. Never publish the key.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include "gts_roots.h"
#include <Preferences.h>
#include <esp_attr.h>
#include "mbedtls/md.h"

// Use the repository's deployed MFCC + NumPy-trained 26->24->4 Stage-1 MLP.
// Including the implementation here keeps this bench sketch tied to the same
// weights and feature code as firmware/node.
#define USE_NN_STAGE1
#if __has_include("../node/stage1.cpp")
#include "../node/stage1.cpp"
#elif __has_include("C:/Users/DELL.000/drone-current/firmware/node/stage1.cpp")
// arduino-cli builds .ino files from a temporary directory, so its preprocessor
// cannot resolve the sibling sketch. This fallback is for the current bench PC.
#include "C:/Users/DELL.000/drone-current/firmware/node/stage1.cpp"
#else
#error "Stage-1 implementation not found"
#endif

static constexpr int PIN_AO = 4;
static constexpr int PIN_DO = 5;
static constexpr uint16_t DEFAULT_THRESHOLD = 180;
static constexpr unsigned long SAMPLE_MS = 40;
static constexpr unsigned long ALERT_COOLDOWN_MS = 15000;
static constexpr unsigned long WIFI_RETRY_MS = 10000;
static constexpr int STAGE1_SAMPLE_RATE = 16000;
static constexpr int STAGE1_SAMPLES = STAGE1_SAMPLE_RATE * 2;
static constexpr int KY_ADC_SAMPLE_RATE = 8000;
static constexpr int KY_ADC_SAMPLES = KY_ADC_SAMPLE_RATE * 2;
static constexpr float STAGE1_MIN_CONFIDENCE = 0.85f;
static constexpr char CLOUD_RELAY_URL[] = "https://vannikawachh-hub.onrender.com/edge/alert";

Preferences prefs;
String ssid, password, nodeId, host, keyHex;
bool kyEnabled = false;  // Off until a KY-037 is physically connected and tested.
double latitude = 0.0, longitude = 0.0;
uint32_t sequence = 0;
uint16_t threshold = DEFAULT_THRESHOLD;
unsigned long lastAlert = 0, lastWifiAttempt = 0, lastStatus = 0;
uint8_t recentLoud = 0;
float noiseFloor = 30.0f;
bool calibrated = false;
unsigned long calibrationStart = 0;
int lastAdcLow = 0, lastAdcHigh = 0;
uint16_t maxPeakSinceStatus = 0;
static int16_t* stage1Audio = nullptr;

// Capture the KY-037 analogue output at approximately 16 kHz and convert its
// unsigned ADC waveform to centred signed PCM for the existing Stage-1 model.
// This is a prototype path: the KY-037 analogue front end is much noisier than
// the INMP441 used to train/deploy the intended sensing node.
void captureKyStage1Window(uint16_t &peakToPeak, float &rms, float &captureHz) {
  uint64_t sum = 0;
  int low = 4095, high = 0;
  uint32_t captureStarted = micros();
  uint32_t nextSample = micros();
  for (int i = 0; i < KY_ADC_SAMPLES; i++) {
    while ((int32_t)(micros() - nextSample) < 0) { delayMicroseconds(2); }
    int raw = analogRead(PIN_AO);
    stage1Audio[i] = (int16_t)raw;
    sum += (uint32_t)raw;
    if (raw < low) low = raw;
    if (raw > high) high = raw;
    nextSample += 1000000UL / KY_ADC_SAMPLE_RATE;
  }
  uint32_t elapsedUs = micros() - captureStarted;
  captureHz = elapsedUs ? (KY_ADC_SAMPLES * 1000000.0f / elapsedUs) : 0.0f;
  int32_t mean = (int32_t)(sum / KY_ADC_SAMPLES);
  double squares = 0.0;
  // Work backwards so the 8 kHz raw samples can be expanded in-place to the
  // model's 16 kHz input without overwriting samples that are still needed.
  for (int i = KY_ADC_SAMPLES - 1; i >= 0; i--) {
    // KY-037 measurements on this board occupy only a small ADC range. Scale
    // after removing DC, saturating instead of allowing integer wraparound.
    int32_t centred = ((int32_t)stage1Audio[i] - mean) * 64;
    if (centred > 32767) centred = 32767;
    if (centred < -32768) centred = -32768;
    stage1Audio[2 * i] = (int16_t)centred;
    stage1Audio[2 * i + 1] = (int16_t)centred;
    squares += 2.0 * (double)centred * centred;
  }
  peakToPeak = (uint16_t)(high - low);
  rms = (float)(sqrt(squares / STAGE1_SAMPLES) / 32768.0);
}

const char* stage1ClassName(int cls) {
  switch (cls) {
    case S1_SCREAM: return "scream";
    case S1_CRY: return "cry";
    case S1_HELP: return "help";
    default: return "background";
  }
}

bool validHexKey(const String& value) {
  if (value.length() != 64) return false;
  for (unsigned int i = 0; i < value.length(); i++) {
    if (!isxdigit((unsigned char)value[i])) return false;
  }
  return true;
}

uint8_t hexByte(const String& value, int offset) {
  return (uint8_t)strtoul(value.substring(offset, offset + 2).c_str(), nullptr, 16);
}

String signatureFor(const String& body) {
  uint8_t key[32], digest[32];
  for (int i = 0; i < 32; i++) key[i] = hexByte(keyHex, i * 2);
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (!info || mbedtls_md_hmac(info, key, sizeof(key),
       (const unsigned char*)body.c_str(), body.length(), digest) != 0) return "";
  static const char hex[] = "0123456789abcdef";
  char output[65];
  for (int i = 0; i < 32; i++) {
    output[i * 2] = hex[digest[i] >> 4];
    output[i * 2 + 1] = hex[digest[i] & 15];
  }
  output[64] = 0;
  return String(output);
}

String signatureForClip(uint32_t seq, const uint8_t* audio, size_t length) {
  uint8_t key[32], digest[32];
  for (int i = 0; i < 32; i++) key[i] = hexByte(keyHex, i * 2);
  String prefix = nodeId + ":" + String(seq) + ":";
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_context_t context;
  mbedtls_md_init(&context);
  if (!info || mbedtls_md_setup(&context, info, 1) != 0) {
    mbedtls_md_free(&context); return "";
  }
  int result = mbedtls_md_hmac_starts(&context, key, sizeof(key));
  if (result == 0) result = mbedtls_md_hmac_update(
      &context, (const unsigned char*)prefix.c_str(), prefix.length());
  if (result == 0) result = mbedtls_md_hmac_update(&context, audio, length);
  if (result == 0) result = mbedtls_md_hmac_finish(&context, digest);
  mbedtls_md_free(&context);
  if (result != 0) return "";
  static const char hex[] = "0123456789abcdef";
  char output[65];
  for (int i = 0; i < 32; i++) {
    output[i * 2] = hex[digest[i] >> 4];
    output[i * 2 + 1] = hex[digest[i] & 15];
  }
  output[64] = 0;
  return String(output);
}

bool readyToSend() {
  return WiFi.status() == WL_CONNECTED && host.length() && nodeId.length() &&
         validHexKey(keyHex) && latitude >= -90 && latitude <= 90 &&
         longitude >= -180 && longitude <= 180 &&
         (latitude != 0.0 || longitude != 0.0);
}

bool sendAlert(float score) {
  if (!readyToSend()) {
    Serial.println("ALERT NOT SENT: Wi-Fi, host, node, key, or coordinates missing");
    return false;
  }
  sequence++;
  prefs.putULong("seq", sequence);  // Never reuse a counter after reboot.
  String body = "{\"node_id\":\"" + nodeId + "\",\"seq\":" + String(sequence) +
                ",\"kind\":\"sound_level_candidate\",\"lat\":" + String(latitude, 7) +
                ",\"lon\":" + String(longitude, 7) +
                ",\"sound_score\":" + String(score, 3) + "}";
  String signature = signatureFor(body);
  if (!signature.length()) return false;
  bool directAccepted = false;
  for (int attempt = 1; attempt <= 2; attempt++) {
    HTTPClient http;
    http.setTimeout(2500);
    if (!http.begin("http://" + host + ":8765/alert")) return false;
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Alert-Signature", signature);
    int result = http.POST((uint8_t*)body.c_str(), body.length());
    String response = http.getString();
    http.end();
    Serial.printf("ALERT seq=%lu attempt=%d HTTP=%d %s\n",
                  (unsigned long)sequence, attempt, result, response.c_str());
    if (result == 200 || (result == 400 && response.indexOf("duplicate") >= 0)) {
      directAccepted = true;
      break;
    }
    delay(400);
  }

  // Also post the identical signed body to the HTTPS cloud relay. The Pi polls
  // that relay when not on the node's LAN; sequence-based dedupe makes receiving
  // the direct and cloud copies safe. Certificate validation uses the public
  // Google Trust Services roots used by the current Render certificate.
  bool cloudAccepted = false;
  WiFiClientSecure tls;
  tls.setCACert(VANNI_GTS_ROOTS);
  HTTPClient cloud;
  cloud.setTimeout(7000);
  if (cloud.begin(tls, CLOUD_RELAY_URL)) {
    cloud.addHeader("Content-Type", "application/json");
    cloud.addHeader("X-Alert-Signature", signature);
    int result = cloud.POST((uint8_t*)body.c_str(), body.length());
    String response = cloud.getString();
    cloud.end();
    Serial.printf("CLOUD seq=%lu HTTPS=%d %s\n", (unsigned long)sequence,
                  result, response.c_str());
    cloudAccepted = result == 200 || result == 202;
  } else {
    Serial.println("CLOUD: HTTPS setup failed; direct LAN path attempted");
  }
  Serial.printf("ALERT paths: direct=%s cloud=%s (no flight command from ESP)\n",
                directAccepted ? "accepted" : "not-confirmed",
                cloudAccepted ? "accepted" : "not-confirmed");
  return directAccepted || cloudAccepted;
}

bool sendCapturedAudio(uint32_t seq) {
  if (!readyToSend() || !stage1Audio) return false;
  const uint8_t* pcm = (const uint8_t*)stage1Audio;
  const size_t bytes = STAGE1_SAMPLES * sizeof(int16_t);
  String signature = signatureForClip(seq, pcm, bytes);
  if (!signature.length()) return false;
  HTTPClient http;
  http.setTimeout(9000);
  if (!http.begin("http://" + host + ":8765/audio")) return false;
  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("X-Node-Id", nodeId);
  http.addHeader("X-Alert-Seq", String(seq));
  http.addHeader("X-Audio-Signature", signature);
  int status = http.POST((uint8_t*)pcm, bytes);
  String response = http.getString();
  http.end();
  Serial.printf("AUDIO seq=%lu bytes=%u HTTP=%d %s\n",
                (unsigned long)seq, (unsigned)bytes, status, response.c_str());
  return status == 200;
}

void printStatus() {
  Serial.printf("WiFi=%s IP=%s Pi=%s node=%s coords=%.7f,%.7f key=%s seq=%lu KY=%s threshold=%u floor=%.0f stage1=mfcc_mlp\n",
                WiFi.status() == WL_CONNECTED ? "connected" : "disconnected",
                WiFi.localIP().toString().c_str(), host.c_str(), nodeId.c_str(),
                latitude, longitude, validHexKey(keyHex) ? "set" : "missing",
                (unsigned long)sequence, kyEnabled ? "on" : "off", threshold,
                noiseFloor);
}

void handleCommand(String line) {
  line.trim();
  int space = line.indexOf(' ');
  String command = space < 0 ? line : line.substring(0, space);
  String value = space < 0 ? "" : line.substring(space + 1);
  if (command == "WIFI") {
    int sep = value.indexOf('|');
    if (sep < 1 || sep == value.length() - 1) { Serial.println("Use WIFI SSID|password"); return; }
    ssid = value.substring(0, sep); password = value.substring(sep + 1);
    prefs.putString("ssid", ssid); prefs.putString("pass", password);
    WiFi.disconnect(); lastWifiAttempt = 0; Serial.println("Wi-Fi saved");
  } else if (command == "NODE") {
    int a = value.indexOf('|'), b = value.indexOf('|', a + 1);
    if (a < 1 || b < a + 2) { Serial.println("Use NODE id|lat|lon"); return; }
    String candidateId = value.substring(0, a);
    for (unsigned int i = 0; i < candidateId.length(); i++) {
      if (!isalnum((unsigned char)candidateId[i]) && candidateId[i] != '-') {
        Serial.println("Node ID must contain only letters, numbers, or hyphens"); return;
      }
    }
    double lat = value.substring(a + 1, b).toDouble();
    double lon = value.substring(b + 1).toDouble();
    if ((lat == 0.0 && lon == 0.0) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      Serial.println("Invalid coordinates"); return;
    }
    nodeId = candidateId; latitude = lat; longitude = lon;
    prefs.putString("node", nodeId); prefs.putDouble("lat", latitude); prefs.putDouble("lon", longitude);
    Serial.println("Node and coordinates saved");
  } else if (command == "KEY") {
    if (!validHexKey(value)) { Serial.println("KEY needs 64 hex characters"); return; }
    keyHex = value; prefs.putString("key", keyHex); Serial.println("Key saved");
  } else if (command == "HOST") {
    IPAddress address;
    if (!address.fromString(value)) { Serial.println("HOST needs Pi IPv4 address"); return; }
    host = value; prefs.putString("host", host); Serial.println("Pi address saved");
  } else if (command == "THRESH") {
    int proposed = value.toInt();
    if (proposed < 30 || proposed > 2500) { Serial.println("THRESH range 30..2500"); return; }
    threshold = proposed; prefs.putUShort("thresh", threshold); Serial.println("Threshold saved");
  } else if (command == "KY") {
    if (value != "0" && value != "1") { Serial.println("Use KY 0 or KY 1"); return; }
    kyEnabled = value == "1";
    prefs.putBool("ky", kyEnabled);
    calibrated = false;
    calibrationStart = millis();
    Serial.printf("KY-037 path %s\n", kyEnabled ? "enabled" : "disabled");
  } else if (command == "STATUS") {
    printStatus();
  } else if (command == "TEST") {
    Serial.println("Sending a BENCH TEST sound-level candidate");
    sendAlert(0.8f);
  } else {
    Serial.println("Commands: WIFI, NODE, KEY, HOST, THRESH, KY, STATUS, TEST");
  }
}

uint16_t sampleSound() {
  int low = 4095, high = 0;
  unsigned long until = millis() + SAMPLE_MS;
  while (millis() < until) {
    int value = analogRead(PIN_AO);
    if (value < low) low = value;
    if (value > high) high = value;
    delayMicroseconds(100);
  }
  lastAdcLow = low;
  lastAdcHigh = high;
  return (uint16_t)(high - low);
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);
  pinMode(PIN_DO, INPUT);
  analogReadResolution(12);
  prefs.begin("vanni-wifi", false);
  ssid = prefs.getString("ssid", ""); password = prefs.getString("pass", "");
  nodeId = prefs.getString("node", ""); host = prefs.getString("host", "");
  keyHex = prefs.getString("key", "");
  latitude = prefs.getDouble("lat", 0.0); longitude = prefs.getDouble("lon", 0.0);
  sequence = prefs.getULong("seq", 0);
  threshold = prefs.getUShort("thresh", DEFAULT_THRESHOLD);
  kyEnabled = prefs.getBool("ky", false);
  stage1Audio = (int16_t*)ps_malloc(STAGE1_SAMPLES * sizeof(int16_t));
  if (!stage1Audio) {
    Serial.println("FATAL: unable to allocate Stage 1 audio buffer in PSRAM");
    kyEnabled = false;
  } else {
    Serial.printf("Stage 1 PSRAM buffer ready: %u bytes\n",
                  (unsigned)(STAGE1_SAMPLES * sizeof(int16_t)));
  }
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  stage1_init();
  calibrationStart = millis();
  Serial.println("KY-037 + MFCC/MLP Stage 1 prototype; physical flight locked on Pi");
  printStatus();
}

void loop() {
  if (Serial.available()) handleCommand(Serial.readStringUntil('\n'));
  if (WiFi.status() != WL_CONNECTED && ssid.length() && millis() - lastWifiAttempt > WIFI_RETRY_MS) {
    lastWifiAttempt = millis();
    WiFi.begin(ssid.c_str(), password.c_str());
    Serial.println("Connecting to saved Wi-Fi...");
  }
  uint16_t peakToPeak = 0;
  bool digitalLow = false;
  if (kyEnabled) {
    peakToPeak = sampleSound();
    if (peakToPeak > maxPeakSinceStatus) maxPeakSinceStatus = peakToPeak;
    digitalLow = digitalRead(PIN_DO) == LOW;
  }
  if (kyEnabled && !calibrated) {
    // A clap while booting must not raise the floor for minutes afterward.
    noiseFloor = 0.95f * noiseFloor +
                 0.05f * min((float)peakToPeak, noiseFloor * 2.0f + 20.0f);
    if (millis() - calibrationStart >= 5000) {
      calibrated = true;
      Serial.printf("Calibrated noise floor: %.0f\n", noiseFloor);
    }
  } else if (kyEnabled) {
    uint16_t activeThreshold = max((float)threshold, noiseFloor * 3.0f);
    bool loud = peakToPeak >= activeThreshold;
    recentLoud = (uint8_t)((recentLoud << 1) | (loud ? 1 : 0));
    if (!loud) {
      if (peakToPeak < noiseFloor)
        noiseFloor = 0.90f * noiseFloor + 0.10f * peakToPeak;
      else
        noiseFloor = 0.999f * noiseFloor + 0.001f * peakToPeak;
    }
    uint8_t bits = recentLoud & 0x3f;
    int count = 0;
    for (int i = 0; i < 6; i++) count += (bits >> i) & 1;
    if (count >= 4 && millis() - lastAlert >= ALERT_COOLDOWN_MS) {
      recentLoud = 0;
      Serial.printf("LOUDNESS gate p2p=%u threshold=%u DO=%d; capturing Stage 1 window\n",
                    peakToPeak, activeThreshold, digitalLow);
      uint16_t capturePeakToPeak = 0;
      float captureRms = 0.0f;
      float captureHz = 0.0f;
      captureKyStage1Window(capturePeakToPeak, captureRms, captureHz);
      Stage1Result result = stage1_infer(stage1Audio, STAGE1_SAMPLES);
      Serial.printf("STAGE1 class=%s confidence=%.3f capture_p2p=%u rms=%.4f adc_hz=%.1f\n",
                    stage1ClassName(result.cls), result.confidence,
                    capturePeakToPeak, captureRms, captureHz);
      if (result.cls != S1_BACKGROUND && result.confidence >= STAGE1_MIN_CONFIDENCE) {
        lastAlert = millis();
        if (sendAlert(result.confidence)) {
          // The clip is sent only over the local Wi-Fi link to the Pi. The
          // cloud receives the signed alert and later the Pi's result.
          sendCapturedAudio(sequence);
        }
      } else {
        Serial.println("STAGE1 rejected candidate; no alert sent");
      }
    }
  }
  if (millis() - lastStatus >= 3000) {
    lastStatus = millis();
    if (kyEnabled) {
      Serial.printf("KY sound_p2p=%u max_3s=%u ADC_min=%d ADC_max=%d floor=%.0f DO_low=%d WiFi=%d\n",
                    peakToPeak, maxPeakSinceStatus, lastAdcLow, lastAdcHigh,
                    noiseFloor, digitalLow, WiFi.status() == WL_CONNECTED);
    } else {
      Serial.printf("KY disabled; WiFi=%d\n", WiFi.status() == WL_CONNECTED);
    }
    maxPeakSinceStatus = 0;
  }
}
