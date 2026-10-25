// Passive TELEM2 check using ESP32-S3 GPIO18 as the dedicated RX pin.
// This sketch never transmits to Pixhawk and cannot arm or start a mission.
#include <Arduino.h>
#include <HardwareSerial.h>
#include <MAVLink.h>

HardwareSerial pixhawkUart(1);
uint32_t byteCount = 0;
uint32_t messageCount = 0;
uint32_t heartbeatCount = 0;
uint32_t lastReport = 0;

void setup() {
  Serial.begin(115200);
  pixhawkUart.begin(57600, SERIAL_8N1, 18, -1); // RX only; no MAVLink TX
  delay(500);
  Serial.println("Passive Pixhawk TELEM2 probe: RX=GPIO18, 57600 baud");
}

void loop() {
  mavlink_message_t message;
  mavlink_status_t status;
  while (pixhawkUart.available()) {
    const uint8_t value = pixhawkUart.read();
    ++byteCount;
    if (!mavlink_parse_char(MAVLINK_COMM_1, value, &message, &status)) continue;
    ++messageCount;
    if (message.msgid == MAVLINK_MSG_ID_HEARTBEAT) {
      ++heartbeatCount;
      mavlink_heartbeat_t heartbeat;
      mavlink_msg_heartbeat_decode(&message, &heartbeat);
      Serial.printf("HEARTBEAT sys=%u comp=%u type=%u armed=%u\n",
                    message.sysid, message.compid, heartbeat.type,
                    (heartbeat.base_mode & MAV_MODE_FLAG_SAFETY_ARMED) != 0);
    }
  }
  if (millis() - lastReport >= 5000) {
    lastReport = millis();
    Serial.printf("RX bytes=%lu valid MAVLink=%lu heartbeats=%lu\n",
                  static_cast<unsigned long>(byteCount),
                  static_cast<unsigned long>(messageCount),
                  static_cast<unsigned long>(heartbeatCount));
  }
}
