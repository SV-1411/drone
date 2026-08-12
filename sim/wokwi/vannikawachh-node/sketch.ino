/*
  VanniKawachh -- single-board SYSTEM SIMULATION (Wokwi / Arduino-compatible)
  ==========================================================================
  This one ESP32 board plays the whole chain so a committee can watch it work:
     sense -> detect -> build alert (with GPS coords) -> decide -> drone -> kit

  HONEST NOTE (say this to your reviewers):
  A circuit simulator cannot put a real scream into a real microphone or run a
  CNN on live audio -- no simulator can. So here the "microphone loudness" is a
  POTENTIOMETER and the "scream" is the RED BUTTON. Everything after that point
  -- the detection thresholds, the day/night + motion fusion, the alert packet
  with the pole's GPS coordinates, the dispatch decision, and the drone response
  -- is the REAL logic running on the REAL microcontroller. The AI model itself
  is validated separately (Edge Impulse on the ESP32-S3 + the software pipeline
  demo). In the real product this board is only the NODE; the hub (Raspberry Pi
  + PANNs) and the drone (Pixhawk) are separate, already proven in software/SITL.
*/

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>

// ---------- pins ----------
const int PIN_SOUND = 34;   // potentiometer  -> mic loudness  (0..4095)
const int PIN_LDR   = 35;   // photoresistor  -> ambient light (0..4095)
const int PIN_PIR   = 27;   // PIR motion sensor (0/1)
const int PIN_BTN   = 14;   // red button -> "scream now" (active low)
const int PIN_LED_G = 2;    // green: idle / listening
const int PIN_LED_R = 4;    // red:   distress confirmed
const int PIN_LED_B = 5;    // blue:  LoRa packet transmit
const int PIN_BUZZ  = 18;   // buzzer: siren cue
const int PIN_SERVO = 13;   // servo:  first-aid kit release

// ---------- node identity ----------
// A roadside pole node has a fixed, surveyed GPS location -- so the node knows
// exactly where the victim is without any GPS fix delay.
const char* NODE_ID  = "NODE-SITABULDI-01";
const float NODE_LAT = 21.1466;
const float NODE_LON = 79.0889;
const char* DRONE_BASE = "GHRCE (West)";   // nearest station (see hub/config.py)
const float DRONE_SPEED = 15.0;            // m/s cruise, for the ETA
const float BASE_LAT = 21.1051, BASE_LON = 79.0036;

// ---------- tuning (mirrors the real Stage-1 gate) ----------
const int   SOUND_THRESH = 2200;   // loudness above this starts a detection
const float DISPATCH_CONF = 0.60;  // fused confidence needed to launch a drone

Adafruit_SSD1306 oled(128, 64, &Wire, -1);
Servo kit;

// ---------- helpers ----------
double haversine_m(double la1, double lo1, double la2, double lo2) {
  const double R = 6371000.0, d2r = 0.017453292519943295;
  double p1 = la1 * d2r, p2 = la2 * d2r;
  double dp = (la2 - la1) * d2r, dl = (lo2 - lo1) * d2r;
  double a = sin(dp / 2) * sin(dp / 2) + cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2);
  return 2 * R * asin(sqrt(a));
}

void banner(const char* line1, const char* line2, int bar = -1) {
  oled.clearDisplay();
  oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 0);  oled.print("VanniKawachh");
  oled.drawFastHLine(0, 10, 128, SSD1306_WHITE);
  oled.setCursor(0, 16); oled.print(line1);
  oled.setCursor(0, 28); oled.print(line2);
  if (bar >= 0) {
    oled.drawRect(0, 44, 128, 10, SSD1306_WHITE);
    oled.fillRect(2, 46, (int)(124.0 * bar / 100.0), 6, SSD1306_WHITE);
  }
  oled.display();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_BTN, INPUT_PULLUP);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  pinMode(PIN_BUZZ, OUTPUT);
  kit.attach(PIN_SERVO);
  kit.write(0);                       // kit latched
  Wire.begin(21, 22);
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  Serial.println("[BOOT] VanniKawachh node online at " + String(NODE_ID));
  Serial.printf("[BOOT] pole location %.4f, %.4f\n", NODE_LAT, NODE_LON);
}

// ---------- the detection -> response sequence ----------
void respond(float conf, const char* event) {
  // 1) distress confirmed
  digitalWrite(PIN_LED_G, LOW);
  digitalWrite(PIN_LED_R, HIGH);
  tone(PIN_BUZZ, 880, 300);
  char l2[24]; snprintf(l2, sizeof(l2), "%s  %.0f%%", event, conf * 100);
  banner("DISTRESS DETECTED", l2);
  Serial.printf("[STAGE1] event=%s confidence=%.2f -> DISTRESS\n", event, conf);
  delay(900);

  // 2) transmit the sealed alert packet (this is the LoRa uplink)
  for (int i = 0; i < 4; i++) { digitalWrite(PIN_LED_B, HIGH); delay(80);
                                digitalWrite(PIN_LED_B, LOW);  delay(80); }
  Serial.println("[LoRa TX] {");
  Serial.printf("   \"node\": \"%s\",\n", NODE_ID);
  Serial.printf("   \"lat\": %.5f, \"lon\": %.5f,\n", NODE_LAT, NODE_LON);
  Serial.printf("   \"event\": \"%s\", \"confidence\": %.2f\n", event, conf);
  Serial.println("}");

  // 3) hub decision + nearest-drone dispatch
  double dist = haversine_m(BASE_LAT, BASE_LON, NODE_LAT, NODE_LON);
  int eta = (int)(dist / DRONE_SPEED);
  char l1[24]; snprintf(l1, sizeof(l1), "Dispatch: %s", DRONE_BASE);
  char e2[24]; snprintf(e2, sizeof(e2), "ETA %ds  %.1fkm", eta, dist / 1000.0);
  banner(l1, e2);
  Serial.printf("[HUB] dispatch nearest drone from %s (%.0f m, ETA %ds)\n",
                DRONE_BASE, dist, eta);
  delay(1200);

  // 4) drone en route (compressed animation of the flight)
  for (int p = 0; p <= 100; p += 5) {
    banner("Drone en route", "flying to victim", p);
    delay(120);
  }

  // 5) arrive + drop the first-aid kit
  banner("Arrived", "dropping kit...");
  Serial.println("[DRONE] over victim -> releasing first-aid kit");
  for (int a = 0; a <= 90; a += 10) { kit.write(a); delay(40); }
  delay(400);
  kit.write(0);
  banner("KIT DELIVERED", "returning to base", 100);
  Serial.println("[DRONE] kit delivered, RTL");
  delay(1500);

  // 6) reset
  digitalWrite(PIN_LED_R, LOW);
}

void loop() {
  int sound = analogRead(PIN_SOUND);          // mic loudness proxy
  int light = analogRead(PIN_LDR);            // ambient light
  bool motion = digitalRead(PIN_PIR);
  bool button = (digitalRead(PIN_BTN) == LOW);

  digitalWrite(PIN_LED_G, HIGH);              // listening
  int level = map(sound, 0, 4095, 0, 100);
  char l2[24]; snprintf(l2, sizeof(l2), "level %d  %s", level, motion ? "motion" : "     ");
  banner("Listening...", l2, level);

  if (button || sound > SOUND_THRESH) {
    // fuse the cues into a confidence, the way the node's Stage-1 gate does:
    // loud sound is the driver; darkness and motion raise the score.
    float conf = constrain(sound / 4095.0, 0, 1);
    if (light > 3000) conf += 0.12;           // dark scene (night) -> riskier
    if (motion)       conf += 0.10;           // someone is there
    if (button)       conf = max(conf, 0.85f);// explicit scream press
    conf = constrain(conf, 0, 1);

    const char* event = (light > 3000) ? "scream(night)" : "scream";
    if (conf >= DISPATCH_CONF) respond(conf, event);
    else {
      banner("Sound heard", "below threshold");
      Serial.printf("[STAGE1] conf=%.2f < %.2f -> ignore\n", conf, DISPATCH_CONF);
      delay(800);
    }
  }
  delay(120);
}
