/*
  VanniKawachh -- DRONE  (Wokwi, ESP32, auto-builds from diagram.json)
  ====================================================================
  Waits at base. Press the ALERT button (that is the alert arriving from the
  hub over LoRa) and it: arms + spins the 4 rotors, flies (props whirl + OLED
  progress), drops the first-aid kit with a servo, runs the camera, then spins
  down and returns to idle.

  Honest note: Wokwi has no DC-motor part, so the 4 rotors are servos that whirl
  and 4 "throttle" LEDs that ramp with the motor power. The real quadcopter
  flight (BLDC + ESC + Pixhawk) is proven in ArduPilot SITL / Gazebo -- no
  circuit simulator flies a drone. This board proves the drone ELECTRONICS:
  motor arming/throttle, the kit-drop servo, and the camera.
*/

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>

const int BTN      = 14;   // ALERT button (= alert from the hub)
const int CAM_LED  = 2;    // camera recording
const int LED_IDLE = 4;    // green: parked
const int LED_BUSY = 5;    // red: on a mission
const int BUZZ     = 18;
const int PROP_PIN[4] = { 13, 12, 27, 26 };   // 4 rotor servos
const int KIT_PIN  = 25;                        // kit-drop servo

Servo prop[4];
Servo kit;
Adafruit_SSD1306 oled(128, 64, &Wire, -1);

void banner(const char* l1, const char* l2, int bar = -1) {
  oled.clearDisplay();
  oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 0); oled.print("VanniKawachh DRONE");
  oled.drawFastHLine(0, 10, 128, SSD1306_WHITE);
  oled.setCursor(0, 16); oled.print(l1);
  oled.setCursor(0, 28); oled.print(l2);
  if (bar >= 0) { oled.drawRect(0, 44, 128, 10, SSD1306_WHITE);
                  oled.fillRect(2, 46, (int)(124.0 * bar / 100.0), 6, SSD1306_WHITE); }
  oled.display();
}

void whirl(int power, int ms) {          // spin the 4 props at a given power
  unsigned long t0 = millis();
  while (millis() - t0 < (unsigned long)ms) {
    int a = (millis() / 2) % 180;        // whirl angle
    for (int i = 0; i < 4; i++) prop[i].write(power > 10 ? a : 90);
    analogWrite(CAM_LED, 255);           // (cam full on)
    delay(15);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BTN, INPUT_PULLUP);
  pinMode(CAM_LED, OUTPUT);
  pinMode(LED_IDLE, OUTPUT);
  pinMode(LED_BUSY, OUTPUT);
  pinMode(BUZZ, OUTPUT);
  for (int i = 0; i < 4; i++) { prop[i].attach(PROP_PIN[i]); prop[i].write(90); }
  kit.attach(KIT_PIN); kit.write(0);
  Wire.begin(21, 22);
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  digitalWrite(LED_IDLE, HIGH);
  banner("Idle at GHRCE", "waiting for alert");
  Serial.println("[DRONE] idle at base");
}

void flyMission() {
  digitalWrite(LED_IDLE, LOW);
  digitalWrite(LED_BUSY, HIGH);
  digitalWrite(CAM_LED, HIGH);
  tone(BUZZ, 1200, 200);
  Serial.println("[DRONE] alert -> arming 4 rotors");
  banner("ALERT received", "arming rotors...", 0);
  for (int p = 0; p <= 100; p += 10) { whirl(p, 120);      // spin up
    banner("Spinning up", "rotors arming", p); }

  Serial.println("[DRONE] en route to victim");
  for (int p = 0; p <= 100; p += 5) { whirl(100, 120);     // fly
    banner("En route", "flying to victim", p); }

  Serial.println("[DRONE] over victim -> dropping kit");
  banner("Arrived", "dropping kit...", 100);
  for (int a = 0; a <= 90; a += 10) { kit.write(a); whirl(100, 40); }
  delay(400); kit.write(0);
  Serial.println("[DRONE] kit delivered -> RTL");

  banner("KIT DELIVERED", "returning...", 100);
  for (int p = 100; p >= 0; p -= 10) { whirl(p, 120); }    // spin down
  for (int i = 0; i < 4; i++) prop[i].write(90);
  digitalWrite(CAM_LED, LOW);
  digitalWrite(LED_BUSY, LOW);
  digitalWrite(LED_IDLE, HIGH);
  banner("Idle at GHRCE", "waiting for alert");
  Serial.println("[DRONE] landed, idle");
}

void loop() {
  if (digitalRead(BTN) == LOW) {         // alert pressed
    flyMission();
    while (digitalRead(BTN) == LOW) delay(50);
  }
  delay(80);
}
