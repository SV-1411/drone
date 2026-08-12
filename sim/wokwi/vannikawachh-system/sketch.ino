/*
  VanniKawachh -- FULL SYSTEM on one ESP32 (Wokwi, auto-builds + auto-triggers)
  =============================================================================
  One board runs the WHOLE chain so you press ONE thing and watch everything:

    scream -> node detects -> alerts hub -> hub verifies -> dispatches drone
           -> 4 rotors spin -> flies -> drops first-aid kit -> returns

  Why one board? Wokwi simulates only ONE microcontroller per project, so two
  separate boards cannot talk to each other. Putting the node role and the drone
  role on the same ESP32 is how you show the full flow auto-triggering in a
  single running sim. In the real product the node (ESP32-S3) and the drone
  (Pixhawk) are separate units joined by a LoRa link -- shown here as the blue
  "LoRa TX" LED + the internal hand-off. The actual flight is proven in
  ArduPilot SITL; here the drone hardware is the 4 rotor servos + the kit servo.

  Trigger it: press the red SCREAM button, or drag the potentiometer up.
*/

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>

// sensors (node role)
const int PIN_SOUND = 34;   // potentiometer = mic loudness
const int PIN_LDR   = 35;   // photoresistor = light (day/night)
const int PIN_PIR   = 32;   // PIR motion
const int PIN_BTN   = 14;   // red SCREAM button
// indicators
const int LED_IDLE  = 4;    // green: listening
const int LED_ACT   = 5;    // red: distress / mission active
const int LED_LORA  = 15;   // blue: LoRa transmit
const int CAM_LED   = 2;    // white: drone camera
const int BUZZ      = 18;
// drone hardware
const int PROP_PIN[4] = { 13, 12, 27, 26 };   // 4 rotor servos
const int KIT_PIN   = 25;                       // kit-drop servo

const int   SOUND_THRESH = 2200;   // ESP32 ADC 0..4095
const float DISPATCH_CONF = 0.60;
const char* NODE_ID = "NODE-SITABULDI-01";
const float NODE_LAT = 21.1466, NODE_LON = 79.0889;

Servo prop[4], kit;
Adafruit_SSD1306 oled(128, 64, &Wire, -1);

void banner(const char* l1, const char* l2, int bar = -1) {
  oled.clearDisplay();
  oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 0); oled.print("VanniKawachh");
  oled.drawFastHLine(0, 10, 128, SSD1306_WHITE);
  oled.setCursor(0, 16); oled.print(l1);
  oled.setCursor(0, 28); oled.print(l2);
  if (bar >= 0) { oled.drawRect(0, 44, 128, 10, SSD1306_WHITE);
                  oled.fillRect(2, 46, (int)(124.0 * bar / 100.0), 6, SSD1306_WHITE); }
  oled.display();
}

void whirl(int ms) {                 // spin the 4 rotors for ms milliseconds
  unsigned long t0 = millis();
  while (millis() - t0 < (unsigned long)ms) {
    int a = (millis() / 2) % 180;
    for (int i = 0; i < 4; i++) prop[i].write(a);
    delay(15);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_BTN, INPUT_PULLUP);
  pinMode(LED_IDLE, OUTPUT); pinMode(LED_ACT, OUTPUT); pinMode(LED_LORA, OUTPUT);
  pinMode(CAM_LED, OUTPUT);  pinMode(BUZZ, OUTPUT);
  for (int i = 0; i < 4; i++) { prop[i].attach(PROP_PIN[i]); prop[i].write(90); }
  kit.attach(KIT_PIN); kit.write(0);
  Wire.begin(21, 22);
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  digitalWrite(LED_IDLE, HIGH);
  banner("Listening...", "waiting for scream");
  Serial.println("[NODE] online at " + String(NODE_ID));
}

void runDrone() {                    // the drone launch + delivery
  digitalWrite(CAM_LED, HIGH);
  banner("Drone: arming", "spinning rotors", 0);
  Serial.println("[DRONE] arming 4 rotors");
  for (int p = 0; p <= 100; p += 10) { whirl(120); banner("Drone: arming", "rotors up", p); }
  Serial.println("[DRONE] en route to victim");
  for (int p = 0; p <= 100; p += 5) { whirl(120); banner("Drone en route", "flying to victim", p); }
  banner("Arrived", "dropping kit...", 100);
  Serial.println("[DRONE] dropping first-aid kit");
  for (int a = 0; a <= 90; a += 10) { kit.write(a); whirl(40); }
  delay(400); kit.write(0);
  banner("KIT DELIVERED", "returning to base", 100);
  Serial.println("[DRONE] kit delivered, RTL");
  for (int p = 100; p >= 0; p -= 10) whirl(120);
  for (int i = 0; i < 4; i++) prop[i].write(90);
  digitalWrite(CAM_LED, LOW);
}

void handleDistress(float conf, const char* ev) {
  // Stage 1: node confirms
  digitalWrite(LED_IDLE, LOW); digitalWrite(LED_ACT, HIGH);
  tone(BUZZ, 880, 300);
  char c[24]; snprintf(c, sizeof(c), "%s %.0f%%", ev, conf * 100);
  banner("DISTRESS DETECTED", c);
  Serial.printf("[STAGE1] %s conf=%.2f\n", ev, conf);
  delay(900);

  // LoRa uplink to the hub
  for (int i = 0; i < 4; i++) { digitalWrite(LED_LORA, HIGH); delay(80);
                                digitalWrite(LED_LORA, LOW);  delay(80); }
  Serial.printf("[LoRa TX] node=%s lat=%.5f lon=%.5f event=%s conf=%.2f\n",
                NODE_ID, NODE_LAT, NODE_LON, ev, conf);
  banner("Alerting hub", "LoRa uplink...");
  delay(700);

  // Stage 2: hub verify + dispatch
  banner("Hub verifying", "PANNs Stage-2...");
  Serial.println("[HUB] Stage-2 verify -> confirmed");
  delay(1200);
  banner("Dispatch nearest", "drone: GHRCE");
  Serial.println("[HUB] dispatch nearest drone from GHRCE");
  delay(800);

  runDrone();

  digitalWrite(LED_ACT, LOW); digitalWrite(LED_IDLE, HIGH);
  banner("Listening...", "waiting for scream");
}

void loop() {
  int sound = analogRead(PIN_SOUND);
  int light = analogRead(PIN_LDR);
  bool motion = digitalRead(PIN_PIR);
  bool btn = (digitalRead(PIN_BTN) == LOW);

  digitalWrite(LED_IDLE, HIGH);
  int level = map(sound, 0, 4095, 0, 100);
  char l2[24]; snprintf(l2, sizeof(l2), "level %d %s", level, motion ? "motion" : "");
  banner("Listening...", l2, level);

  if (btn || sound > SOUND_THRESH) {
    float conf = constrain(sound / 4095.0, 0, 1);
    if (light > 3000) conf += 0.12;
    if (motion)       conf += 0.10;
    if (btn && conf < 0.85) conf = 0.85;
    conf = constrain(conf, 0, 1);
    const char* ev = (light > 3000) ? "scream(night)" : "scream";
    if (conf >= DISPATCH_CONF) handleDistress(conf, ev);
    else { banner("Sound heard", "below threshold"); delay(700); }
  }
  delay(120);
}
