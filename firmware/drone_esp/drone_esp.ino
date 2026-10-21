/*
 * Drone-mounted ESP32-S3: Render verified-incident queue <-> Pixhawk TELEM2.
 * No microphone or sensing-node code runs on this board.
 *
 * USB serial provisioning (115200):
 *   WIFI <SSID>|<password>
 *   TOKEN <VANNI_DRONE_ESP_TOKEN>
 *   STATUS
 * The Wi-Fi settings and token are kept in ESP NVS, not in source control.
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <time.h>
#include <MAVLink.h>
#include "gts_roots.h"
#include "pixhawk_mission_bridge.h"

static constexpr char RELAY[] = "https://vannikawachh-hub.onrender.com";
static constexpr uint32_t POLL_MS = 3000;
static constexpr uint32_t TELEMETRY_MS = 10000;
static constexpr uint32_t WIFI_RETRY_MS = 10000;

Preferences prefs;
PixhawkMissionBridge pixhawk;
String wifiName, wifiPassword, token, activeCommand, resultStatus, resultDetail;
uint32_t lastPoll = 0, lastTelemetry = 0, lastWifiTry = 0;

bool cloudReady() {
  return WiFi.status() == WL_CONNECTED && token.length() >= 32 &&
         time(nullptr) > 1700000000;
}

int postJson(const String& path, const String& body, String& reply) {
  WiFiClientSecure tls;
  tls.setCACert(VANNI_GTS_ROOTS);
  HTTPClient http;
  http.setTimeout(5000);
  if (!http.begin(tls, String(RELAY) + path)) return -1;
  http.addHeader("Authorization", "Bearer " + token);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  if (code > 0) reply = http.getString();
  http.end();
  return code;
}

void claimNext() {
  String response;
  int code = postJson("/edge/drone/claim/next", "{}", response);
  if (code != 200) {
    Serial.printf("Render claim HTTP=%d\n", code);
    return;
  }
  DynamicJsonDocument document(1024);
  if (deserializeJson(document, response)) {
    Serial.println("Render claim: invalid JSON");
    return;
  }
  JsonVariant command = document["command"];
  if (command.isNull()) return;
  String id = command["id"] | "";
  double lat = command["lat"] | 0.0;
  double lon = command["lon"] | 0.0;
  if (!id.length() || id.length() > 100) return;
  activeCommand = id;
  if (!pixhawk.queueDistress(lat, lon)) {
    resultStatus = "rejected";
    resultDetail = "invalid destination or Pixhawk mission busy";
  }
  Serial.printf("Render command claimed id=%s target=%.7f,%.7f\n",
                activeCommand.c_str(), lat, lon);
}

void reportResult() {
  if (!activeCommand.length() || !resultStatus.length()) return;
  DynamicJsonDocument document(512);
  document["status"] = resultStatus;
  document["detail"] = resultDetail;
  String body, reply;
  serializeJson(document, body);
  int code = postJson("/edge/drone/result/" + activeCommand, body, reply);
  Serial.printf("Render result HTTP=%d status=%s\n", code, resultStatus.c_str());
  if (code == 200) {
    activeCommand = "";
    resultStatus = "";
    resultDetail = "";
  }
}

void reportTelemetry() {
  DynamicJsonDocument document(512);
  document["heartbeat"] = pixhawk.heartbeatFresh();
  document["gps_fix"] = pixhawk.gpsFix();
  document["satellites"] = pixhawk.satellites();
  document["armed"] = pixhawk.armed();
  document["mission_state"] = pixhawk.missionState();
  String body, reply;
  serializeJson(document, body);
  int code = postJson("/edge/drone/telemetry", body, reply);
  if (code != 200) Serial.printf("Render telemetry HTTP=%d\n", code);
}

void handleSerial(String line) {
  line.trim();
  if (line.startsWith("WIFI ")) {
    String value = line.substring(5);
    int separator = value.indexOf('|');
    if (separator < 1 || separator >= value.length() - 1) {
      Serial.println("Use WIFI SSID|password"); return;
    }
    wifiName = value.substring(0, separator);
    wifiPassword = value.substring(separator + 1);
    prefs.putString("ssid", wifiName);
    prefs.putString("pass", wifiPassword);
    WiFi.disconnect();
    lastWifiTry = 0;
    Serial.println("Wi-Fi saved");
  } else if (line.startsWith("TOKEN ")) {
    String value = line.substring(6);
    if (value.length() < 32 || value.length() > 200) {
      Serial.println("Token length must be 32..200 characters"); return;
    }
    token = value;
    prefs.putString("token", token);
    Serial.println("Drone ESP token saved");
  } else if (line == "STATUS") {
    Serial.printf("WiFi=%s IP=%s token=%s TLS_time=%s command=%s\n",
                  WiFi.status() == WL_CONNECTED ? "connected" : "offline",
                  WiFi.localIP().toString().c_str(),
                  token.length() >= 32 ? "set" : "missing",
                  time(nullptr) > 1700000000 ? "ready" : "waiting",
                  activeCommand.length() ? activeCommand.c_str() : "none");
    pixhawk.printStatus();
  } else {
    Serial.println("Commands: WIFI SSID|password, TOKEN value, STATUS");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);
  prefs.begin("vanni-drone", false);
  wifiName = prefs.getString("ssid", "");
  wifiPassword = prefs.getString("pass", "");
  token = prefs.getString("token", "");
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  pixhawk.begin();
  Serial.println("Drone ESP cloud/MAVLink bridge ready");
}

void loop() {
  pixhawk.tick();
  if (Serial.available()) handleSerial(Serial.readStringUntil('\n'));

  uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED && wifiName.length() &&
      now - lastWifiTry >= WIFI_RETRY_MS) {
    lastWifiTry = now;
    WiFi.begin(wifiName.c_str(), wifiPassword.c_str());
  }

  String detail;
  PixhawkMissionBridge::Outcome outcome = pixhawk.takeOutcome(detail);
  if (outcome != PixhawkMissionBridge::NONE && activeCommand.length()) {
    resultStatus = outcome == PixhawkMissionBridge::UPLOADED
        ? "mission_uploaded" : (outcome == PixhawkMissionBridge::REJECTED
                              ? "rejected" : "failed");
    resultDetail = detail;
  }
  if (!cloudReady()) return;
  if (resultStatus.length()) {
    if (now - lastPoll >= POLL_MS) {
      lastPoll = now;
      reportResult();
    }
    return;
  }
  if (activeCommand.length()) return;
  if (now - lastPoll >= POLL_MS) {
    lastPoll = now;
    claimNext();
    pixhawk.tick();
  }
  if (activeCommand.length()) return;
  if (millis() - lastTelemetry >= TELEMETRY_MS) {
    lastTelemetry = millis();
    reportTelemetry();
  }
}
