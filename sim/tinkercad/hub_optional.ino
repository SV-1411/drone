/*
  VanniKawachh -- HUB  (Tinkercad, Arduino Uno)  [OPTIONAL 3rd board]
  ==================================================================
  Represents the Raspberry Pi 5 hub. It sits BETWEEN the node and the drone and
  adds the second verification stage (in the real product this is the PANNs
  audio model on the Pi). Here it "verifies" for a moment, and only then passes
  the alert to the drone -- that two-stage check (node Stage-1 + hub Stage-2) is
  the core idea of the project, so showing it is worth the extra board.

  Insert it like this:  node D8 -> hub D2 (in) ;  hub D8 (out) -> drone D2.
  All three Unos share a common GND.

  Wiring: ALERT in->D2, verify LED (yellow)->D4, verified LED (green)->D5,
  ALERT out->D8.
*/

const int ALERT_IN  = 2;   // from the node
const int LED_VERIFY = 4;   // yellow: running Stage-2 check
const int LED_OK     = 5;   // green: verified distress
const int ALERT_OUT = 8;   // to the drone

void setup() {
  Serial.begin(9600);
  pinMode(ALERT_IN, INPUT);
  pinMode(LED_VERIFY, OUTPUT);
  pinMode(LED_OK, OUTPUT);
  pinMode(ALERT_OUT, OUTPUT);
  digitalWrite(ALERT_OUT, LOW);
  Serial.println("[HUB] Raspberry Pi hub online, Stage-2 verifier ready");
}

void loop() {
  if (digitalRead(ALERT_IN) == HIGH) {
    Serial.println("[HUB] node alert in -> running Stage-2 (PANNs) verification");
    // simulate the verification pass
    for (int i = 0; i < 6; i++) { digitalWrite(LED_VERIFY, HIGH); delay(150);
                                  digitalWrite(LED_VERIFY, LOW);  delay(150); }
    // verified -> dispatch the nearest drone
    digitalWrite(LED_OK, HIGH);
    digitalWrite(ALERT_OUT, HIGH);
    Serial.println("[HUB] VERIFIED -> dispatching nearest drone");
    while (digitalRead(ALERT_IN) == HIGH) delay(50);   // hold until node clears
    digitalWrite(ALERT_OUT, LOW);
    digitalWrite(LED_OK, LOW);
    Serial.println("[HUB] mission handed off, back to listening");
  }
  delay(100);
}
