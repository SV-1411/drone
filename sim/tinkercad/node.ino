/*
  VanniKawachh -- SENSOR NODE  (Tinkercad, Arduino Uno)
  =====================================================
  The roadside pole. Senses distress and raises an alert line to the drone
  (that alert line is the LoRa uplink in the real product).

  Honest note: a simulator cannot feed a real scream into a real mic, so here
  the POTENTIOMETER is the microphone loudness and the RED BUTTON is "a scream".
  Everything after that -- the threshold, the day/night + motion fusion, the
  alert packet with this pole's GPS coordinates -- is the real node logic.

  Wiring (see README): pot->A0, LDR->A1, PIR->D2, button->D3, greenLED->D4,
  redLED->D5, blueLED->D6, buzzer->D7, ALERT out->D8 (goes to the drone's D2).
  IMPORTANT: connect this Uno's GND to the drone Uno's GND (shared ground).
*/

const int PIN_SOUND = A0;   // potentiometer = mic loudness (0..1023)
const int PIN_LDR   = A1;   // photoresistor = ambient light
const int PIN_PIR   = 2;    // PIR motion
const int PIN_BTN   = 3;    // red button = "scream" (INPUT_PULLUP, active low)
const int LED_G     = 4;    // green: listening
const int LED_R     = 5;    // red: distress
const int LED_B     = 6;    // blue: LoRa transmit
const int BUZZ      = 7;    // buzzer
const int ALERT_OUT = 8;    // HIGH tells the drone to launch

const int   SOUND_THRESH = 600;    // Uno ADC 0..1023
const float DISPATCH_CONF = 0.60;

const char* NODE_ID  = "NODE-SITABULDI-01";
const float NODE_LAT = 21.1466;    // this pole's surveyed location
const float NODE_LON = 79.0889;

void setup() {
  Serial.begin(9600);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_BTN, INPUT_PULLUP);
  pinMode(LED_G, OUTPUT); pinMode(LED_R, OUTPUT); pinMode(LED_B, OUTPUT);
  pinMode(BUZZ, OUTPUT);  pinMode(ALERT_OUT, OUTPUT);
  digitalWrite(ALERT_OUT, LOW);
  Serial.println("[NODE] online at NODE-SITABULDI-01 (21.1466, 79.0889)");
}

void sendAlert(float conf, const char* ev) {
  digitalWrite(LED_G, LOW);
  digitalWrite(LED_R, HIGH);
  tone(BUZZ, 880, 300);

  // the sealed LoRa alert packet
  Serial.print("[LoRa TX] node="); Serial.print(NODE_ID);
  Serial.print(" lat=");  Serial.print(NODE_LAT, 5);
  Serial.print(" lon=");  Serial.print(NODE_LON, 5);
  Serial.print(" event="); Serial.print(ev);
  Serial.print(" conf="); Serial.println(conf);
  for (int i = 0; i < 4; i++) { digitalWrite(LED_B, HIGH); delay(80);
                                digitalWrite(LED_B, LOW);  delay(80); }

  digitalWrite(ALERT_OUT, HIGH);   // raise the line -> drone launches
  delay(6000);                     // hold while the drone flies the mission
  digitalWrite(ALERT_OUT, LOW);
  digitalWrite(LED_R, LOW);
}

void loop() {
  int sound = analogRead(PIN_SOUND);
  int light = analogRead(PIN_LDR);
  bool motion = digitalRead(PIN_PIR);
  bool btn = (digitalRead(PIN_BTN) == LOW);

  digitalWrite(LED_G, HIGH);        // listening

  if (btn || sound > SOUND_THRESH) {
    float conf = sound / 1023.0;
    if (light > 700) conf += 0.12;  // dark scene (night) -> riskier
    if (motion)      conf += 0.10;  // someone is there
    if (btn && conf < 0.85) conf = 0.85;   // explicit scream press
    if (conf > 1) conf = 1;

    const char* ev = (light > 700) ? "scream(night)" : "scream";
    if (conf >= DISPATCH_CONF) sendAlert(conf, ev);
    else { Serial.println("[NODE] sound below threshold, ignoring"); delay(500); }
  }
  delay(100);
}
