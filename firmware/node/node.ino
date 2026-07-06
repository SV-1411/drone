/*
 * VanniKawachh sensing node — ESP32-S3 + INMP441 + PIR + LDR + SX1278.
 *
 * Stage 1 runs here: I2S audio capture -> MFCC -> tiny CNN (TensorFlow Lite
 * Micro). On a distress-like hit the node (a) transmits a sealed 25-byte
 * alert over LoRa and (b) uploads the last 4 s of audio to the hub's clip
 * server over WiFi for Stage-2 (PANNs) verification.
 *
 * Board: ESP32-S3 Dev Module (Arduino core >= 2.0.14)
 * Libraries: LoRa (Sandeep Mistry), WiFi, HTTPClient (bundled), mbedtls (IDF)
 *
 * Wiring (matches docs/HARDWARE_INTEGRATION.md):
 *   INMP441: WS=GPIO4  SCK=GPIO5  SD=GPIO6   (L/R -> GND, VDD 3V3)
 *   SX1278 : SCK=GPIO12 MISO=GPIO13 MOSI=GPIO11 NSS=GPIO10 RST=GPIO9 DIO0=GPIO8
 *   PIR    : OUT=GPIO7      LDR divider: GPIO1 (ADC)
 *
 * NOTE ON THE MODEL: stage1_score() below is where the trained TFLM model
 * plugs in (micro_speech-style CNN over MFCCs; classes: scream / help /
 * bachao / cry / background). Until Phase 1 training lands, a calibrated
 * energy+band heuristic stands in so the full chain can be exercised.
 */

#include <driver/i2s.h>
#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include "mbedtls/aes.h"
#include "mbedtls/md.h"

// ------------------------- configuration -----------------------------------
static const uint16_t NODE_ID       = 1;
static const char*    WIFI_SSID     = "VANNIKAWACHH-HUB";
static const char*    WIFI_PASS     = "changeme123";
static const char*    HUB_CLIP_URL  = "http://192.168.4.1:8990/clip"; // + /id/ctr
static const long     LORA_FREQ     = 433E6;
// AES master key — MUST match HUB_MASTER_KEY on the hub (dev key below).
static const uint8_t  MASTER_KEY[16] =
  {0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f};

static const int PIN_PIR = 7, PIN_LDR = 1;
static const int I2S_WS = 4, I2S_SCK = 5, I2S_SD = 6;
static const int LORA_NSS = 10, LORA_RST = 9, LORA_DIO0 = 8;

static const int   SAMPLE_RATE   = 16000;
static const int   FRAME_SAMPLES = 512;                 // 32 ms frames
static const int   CLIP_SECONDS  = 4;
static const float TRIGGER_SCORE = 0.60f;               // stage-1 recall-tuned

// ------------------------- state -------------------------------------------
// The audio ring and the upload buffer are large (~128 KB each). Place them in
// PSRAM so they do not exhaust internal SRAM. Enable PSRAM in the board menu
// (Arduino: "OPI PSRAM" for the ESP32-S3). If your board has no PSRAM, lower
// CLIP_SECONDS to 2 and drop the EXT_RAM_BSS_ATTR.
EXT_RAM_BSS_ATTR static int16_t clipBuf[SAMPLE_RATE * CLIP_SECONDS];  // ring
static size_t   clipPos = 0;
static uint32_t txCounter = 0;

// The alert counter MUST survive reboots. If it reset to 0 on every power-up,
// the hub would reject every packet after the first boot as a replay. We keep
// it in NVS (survives power loss) and load it in setup().
Preferences prefs;

// ------------------------- audio capture -----------------------------------
void i2sInit() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = SAMPLE_RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;      // INMP441 is 24-in-32
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.dma_buf_count = 4;
  cfg.dma_buf_len = FRAME_SAMPLES;
  i2s_driver_install(I2S_NUM_0, &cfg, 0, nullptr);
  i2s_pin_config_t pins = {};
  pins.bck_io_num = I2S_SCK; pins.ws_io_num = I2S_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE; pins.data_in_num = I2S_SD;
  i2s_set_pin(I2S_NUM_0, &pins);
}

size_t readFrame(int16_t* out, size_t n) {
  static int32_t raw[FRAME_SAMPLES];
  size_t bytesRead = 0;
  i2s_read(I2S_NUM_0, raw, n * sizeof(int32_t), &bytesRead, portMAX_DELAY);
  size_t got = bytesRead / sizeof(int32_t);
  for (size_t i = 0; i < got; i++) out[i] = (int16_t)(raw[i] >> 14);
  return got;
}

// ------------------------- Stage 1 ------------------------------------------
// >>> Phase-1 deliverable: replace with MFCC + TFLM CNN invoke() <<<
// The heuristic below approximates "loud + high-band burst" so the chain is
// testable end-to-end before the trained model is flashed.
float stage1_score(const int16_t* x, size_t n) {
  double energy = 0, hi = 0;
  int16_t prev = 0;
  for (size_t i = 0; i < n; i++) {
    energy += (double)x[i] * x[i];
    double d = (double)x[i] - prev;                     // crude HPF
    hi += d * d;
    prev = x[i];
  }
  float rms  = sqrtf(energy / n) / 32768.0f;
  float band = (energy > 0) ? (float)(hi / (4.0 * energy)) : 0.0f;
  float loud = fminf(1.0f, rms / 0.08f);
  return 0.6f * loud + 0.4f * fminf(1.0f, band);
}

// ------------------------- packet sealing (mirrors hub/packets.py) ---------
void deriveNodeKey(uint8_t out[16]) {
  char msg[16]; int mlen = snprintf(msg, sizeof(msg), "node:%u", NODE_ID);
  uint8_t full[32];
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),
                  MASTER_KEY, 16, (const uint8_t*)msg, mlen, full);
  memcpy(out, full, 16);
}

// packet: "VK" ver nodeId ctr | AES-CTR(payload 8B) | HMAC[:8]  == 25 bytes
size_t buildPacket(uint8_t* pkt, uint8_t event, float conf,
                   bool pir, uint8_t light, uint8_t batt) {
  uint8_t key[16]; deriveNodeKey(key);
  txCounter++;
  prefs.putUInt("ctr", txCounter);          // persist so reboots keep counting
  pkt[0]='V'; pkt[1]='K'; pkt[2]=1;
  pkt[3]=NODE_ID>>8; pkt[4]=NODE_ID&0xFF;
  pkt[5]=txCounter>>24; pkt[6]=txCounter>>16; pkt[7]=txCounter>>8; pkt[8]=txCounter;
  uint8_t payload[8] = { event, (uint8_t)(conf*255.0f),
                         (uint8_t)(pir?1:0), light, batt, 0,0,0 };
  uint8_t iv[16]; memcpy(iv, pkt, 9); memset(iv+9, 0, 7);
  uint8_t sb[16]; size_t nc = 0; size_t off = 0;
  mbedtls_aes_context aes; mbedtls_aes_init(&aes);
  mbedtls_aes_setkey_enc(&aes, key, 128);
  mbedtls_aes_crypt_ctr(&aes, 8, &nc, iv, sb, payload, pkt+9);
  mbedtls_aes_free(&aes);
  uint8_t mac[32];
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),
                  key, 16, pkt, 17, mac);
  memcpy(pkt+17, mac, 8);
  return 25;
}

// ------------------------- alert actions -----------------------------------
void sendLoraAlert(float conf, bool pir, uint8_t light) {
  uint8_t pkt[25];
  buildPacket(pkt, /*event=scream*/1, conf, pir, light, /*batt%*/90);
  LoRa.beginPacket(); LoRa.write(pkt, 25); LoRa.endPacket();
  Serial.printf("[node] LoRa alert sent (ctr=%lu conf=%.2f)\n",
                (unsigned long)txCounter, conf);
}

void uploadClip() {
  if (WiFi.status() != WL_CONNECTED) { Serial.println("[node] no WiFi — clip skipped"); return; }
  HTTPClient http;
  char url[96];
  snprintf(url, sizeof(url), "%s/%u/%lu", HUB_CLIP_URL, NODE_ID,
           (unsigned long)txCounter);
  http.begin(url);
  http.addHeader("Content-Type", "application/octet-stream");
  // Minimal WAV header + ring buffer contents, oldest-first. In PSRAM so it
  // does not collide with clipBuf in internal SRAM (see the note by clipBuf).
  EXT_RAM_BSS_ATTR static uint8_t wav[44 + sizeof(clipBuf)];
  const uint32_t dataLen = sizeof(clipBuf), sr = SAMPLE_RATE;
  memcpy(wav, "RIFF", 4); *(uint32_t*)(wav+4) = 36 + dataLen;
  memcpy(wav+8, "WAVEfmt ", 8); *(uint32_t*)(wav+16) = 16;
  *(uint16_t*)(wav+20) = 1;  *(uint16_t*)(wav+22) = 1;
  *(uint32_t*)(wav+24) = sr; *(uint32_t*)(wav+28) = sr * 2;
  *(uint16_t*)(wav+32) = 2;  *(uint16_t*)(wav+34) = 16;
  memcpy(wav+36, "data", 4); *(uint32_t*)(wav+40) = dataLen;
  size_t tail = sizeof(clipBuf)/2 - clipPos;
  memcpy(wav+44, clipBuf + clipPos, tail * 2);
  memcpy(wav+44 + tail*2, clipBuf, clipPos * 2);
  int code = http.POST(wav, sizeof(wav));
  Serial.printf("[node] clip upload -> %d\n", code);
  http.end();
}

// ------------------------- setup / loop ------------------------------------
void setup() {
  Serial.begin(115200);
  prefs.begin("vanni", false);                 // NVS namespace
  txCounter = prefs.getUInt("ctr", 0);         // resume the alert counter
  Serial.printf("[node] resumed alert counter at %lu\n", (unsigned long)txCounter);
  pinMode(PIN_PIR, INPUT);
  i2sInit();
  SPI.begin(12, 13, 11, LORA_NSS);
  LoRa.setPins(LORA_NSS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(LORA_FREQ)) Serial.println("[node] LoRa init FAILED");
  LoRa.setSpreadingFactor(9);                          // range/airtime balance
  WiFi.begin(WIFI_SSID, WIFI_PASS);                    // hub AP (best effort)
  Serial.println("[node] VanniKawachh node up");
}

void loop() {
  static int16_t frame[FRAME_SAMPLES];
  static uint32_t lastAlertMs = 0;
  size_t n = readFrame(frame, FRAME_SAMPLES);

  // keep the 4 s ring buffer current
  for (size_t i = 0; i < n; i++) {
    clipBuf[clipPos] = frame[i];
    clipPos = (clipPos + 1) % (sizeof(clipBuf) / 2);
  }

  float score = stage1_score(frame, n);
  if (score >= TRIGGER_SCORE && millis() - lastAlertMs > 15000) {   // 15 s refractory
    lastAlertMs = millis();
    bool pir = digitalRead(PIN_PIR) == HIGH;
    uint8_t light = (uint8_t)(analogRead(PIN_LDR) >> 4);            // 12-bit -> 8-bit
    Serial.printf("[node] STAGE-1 HIT score=%.2f pir=%d light=%u\n", score, pir, light);
    sendLoraAlert(score, pir, light);
    uploadClip();
  }
}
