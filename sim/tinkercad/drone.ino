/*
  VanniKawachh -- DRONE  (Tinkercad, Arduino Uno)
  ===============================================
  The response unit. Waits at base; when the alert line goes HIGH it arms and
  spins up the 4 rotor motors, "flies" (motors run), drops the first-aid kit
  with a servo, runs the camera, then returns and spins down.

  Honest note: a circuit simulator shows the drone's ELECTRONICS (motor arming,
  throttle, kit-drop servo, camera). The actual FLIGHT (BLDC + ESC + Pixhawk +
  aerodynamics) is proven in a flight simulator -- ArduPilot SITL / Gazebo,
  which this project already runs. No circuit sim flies a quadcopter; that split
  is exactly how real drone teams validate hardware.

  Wiring (see README): ALERT in->D2 (from node D8), throttle->D6 (PWM) -> TIP120
  base -> 4 DC motors, kit servo->D10, cameraLED->D4, idleLED(green)->D12,
  busyLED(red)->D13, buzzer->D8. Shared GND with the node Uno.

  Pin choice note: the Servo library uses Timer1 (kills PWM on pins 9 & 10), and
  tone() uses Timer2 (pins 3 & 11), so the motor throttle must use a Timer0 PWM
  pin -> D6. Do not move it to 9/10/3/11 or the throttle stops working.
*/

#include <Servo.h>

const int ALERT_IN = 2;    // from the node (its D8)
const int THROTTLE = 6;    // PWM (Timer0) -> transistor -> 4 rotor motors
const int CAM_LED  = 4;    // camera recording indicator
const int LED_IDLE = 12;   // green: parked at base
const int LED_BUSY = 13;   // red: on a mission
const int BUZZ     = 8;
const int SERVO_PIN = 10;  // first-aid kit release

Servo kit;

void throttle(int pwm) { analogWrite(THROTTLE, pwm); }

void flyMission() {
  digitalWrite(LED_IDLE, LOW);
  digitalWrite(LED_BUSY, HIGH);
  digitalWrite(CAM_LED, HIGH);
  Serial.println("[DRONE] alert received -> arming 4 rotors");

  for (int t = 0; t <= 255; t += 15) { throttle(t); delay(80); }  // spin up
  Serial.println("[DRONE] en route to victim (rotors at full)");
  tone(BUZZ, 1200, 200);
  delay(5000);                                                    // flying

  Serial.println("[DRONE] over victim -> releasing first-aid kit");
  for (int a = 0; a <= 90; a += 10) { kit.write(a); delay(40); }
  delay(600);
  kit.write(0);
  Serial.println("[DRONE] kit delivered -> returning to base");

  for (int t = 255; t >= 0; t -= 15) { throttle(t); delay(80); } // spin down
  digitalWrite(CAM_LED, LOW);
  digitalWrite(LED_BUSY, LOW);
  digitalWrite(LED_IDLE, HIGH);
  Serial.println("[DRONE] landed, idle at base");
}

void setup() {
  Serial.begin(9600);
  pinMode(ALERT_IN, INPUT);
  pinMode(THROTTLE, OUTPUT);
  pinMode(CAM_LED, OUTPUT);
  pinMode(LED_IDLE, OUTPUT);
  pinMode(LED_BUSY, OUTPUT);
  pinMode(BUZZ, OUTPUT);
  kit.attach(SERVO_PIN);
  kit.write(0);
  throttle(0);
  digitalWrite(LED_IDLE, HIGH);
  Serial.println("[DRONE] idle, parked at GHRCE base");
}

void loop() {
  if (digitalRead(ALERT_IN) == HIGH) {
    flyMission();
    // wait for the alert line to drop so we do not immediately re-trigger
    while (digitalRead(ALERT_IN) == HIGH) delay(50);
  }
  delay(100);
}
