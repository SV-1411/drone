/*
  VanniKawachh -- CLOUD-CONNECTED NODE  (Wokwi ESP32 -> your DEPLOYED dashboard)
  =============================================================================
  This is the demo that connects the simulated hardware to the real system:
  the ESP32 in Wokwi detects a scream and sends the alert over WiFi to your
  deployed dashboard on Render. The dashboard then runs the detection pipeline
  and dispatches the nearest drone -- LIVE, in front of the committee.

  Wokwi gives the ESP32 real internet through the "Wokwi-GUEST" network, so this
  actually reaches https://vannikawachh-hub.onrender.com. Open your dashboard in
  a browser next to this, press the SCREAM button here, and watch the dashboard
  light up and launch a drone.

  Trigger: press the red SCREAM button, or drag the potentiometer up.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ---- your deployed dashboard ----
const char* HUB = "https://vannikawachh-hub.onrender.com";
const char* WIFI_SSID = "Wokwi-GUEST";   // Wokwi's built-in internet (no password)
const char* WIFI_PASS = "";

// ---- this node ----
const char* NODE_ID  = "WOKWI-NODE-01";
const float NODE_LAT = 21.1466;          // pole location sent to the hub
const float NODE_LON = 79.0889;

// ---- pins ----
const int PIN_SOUND = 34, PIN_LDR = 35, PIN_PIR = 32, PIN_BTN = 14;
const int LED_IDLE = 4, LED_DIST = 5, LED_TX = 15, BUZZ = 18;
const int SOUND_THRESH = 2200;

Adafruit_SSD1306 oled(128, 64, &Wire, -1);

void banner(const char* l1, const char* l2) {
  oled.clearDisplay();
  oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 0); oled.print("VanniKawachh NODE");
  oled.drawFastHLine(0, 10, 128, SSD1306_WHITE);
  oled.setCursor(0, 16); oled.print(l1);
  oled.setCursor(0, 30); oled.print(l2);
  oled.display();
}

String jsonStr(const String& body, const char* key) {   // tiny "key":"value" reader
  int i = body.indexOf(String("\"") + key + "\":\"");
  if (i < 0) return "";
  i += strlen(key) + 4;
  int j = body.indexOf('"', i);
  return j < 0 ? "" : body.substring(i, j);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PIR, INPUT); pinMode(PIN_BTN, INPUT_PULLUP);
  pinMode(LED_IDLE, OUTPUT); pinMode(LED_DIST, OUTPUT); pinMode(LED_TX, OUTPUT);
  pinMode(BUZZ, OUTPUT);
  Wire.begin(21, 22);
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  banner("Connecting WiFi", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println("\n[NODE] WiFi up, IP " + WiFi.localIP().toString());
  banner("Listening...", "connected to hub");
}

void sendAlert(float conf, int event, int light255) {
  digitalWrite(LED_IDLE, LOW); digitalWrite(LED_DIST, HIGH);
  tone(BUZZ, 880, 250);
  banner("DISTRESS!", "sending to hub...");
  for (int i = 0; i < 3; i++) { digitalWrite(LED_TX, HIGH); delay(70);
                                digitalWrite(LED_TX, LOW);  delay(70); }

  String url = String(HUB) + "/node-alert?node=" + NODE_ID +
               "&lat=" + String(NODE_LAT, 5) + "&lon=" + String(NODE_LON, 5) +
               "&event=" + event + "&conf=" + String(conf, 2) +
               "&pir=1&light=" + light255;
  Serial.println("[NODE] GET " + url);

  WiFiClientSecure client; client.setInsecure();      // skip cert check (demo)
  HTTPClient https; https.begin(client, url);
  int code = https.GET();
  String body = (code > 0) ? https.getString() : "";
  https.end();
  Serial.printf("[NODE] HTTP %d  %s\n", code, body.c_str());

  if (code == 200) {
    String drone = jsonStr(body, "drone");
    banner("Dispatched!", drone.length() ? drone.c_str() : "see dashboard");
  } else {
    banner("Send failed", ("HTTP " + String(code)).c_str());
  }
  delay(3000);
  digitalWrite(LED_DIST, LOW);
  banner("Listening...", "connected to hub");
}

void loop() {
  int sound = analogRead(PIN_SOUND);
  int light = analogRead(PIN_LDR);
  bool btn = (digitalRead(PIN_BTN) == LOW);
  digitalWrite(LED_IDLE, HIGH);

  if (btn || sound > SOUND_THRESH) {
    float conf = constrain(sound / 4095.0, 0, 1);
    if (btn && conf < 0.9) conf = 0.9;
    int event = 1;                                    // 1 = scream
    int light255 = map(light, 0, 4095, 0, 255);
    sendAlert(conf, event, light255);
  }
  delay(120);
}
