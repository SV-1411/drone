/*
 * VanniKawachh LoRa gateway — ESP32 + SX1278, plugged into the hub Pi's USB.
 *
 * Dumb bridge by design: every received LoRa frame is printed as one line
 *     RX <hex-bytes> RSSI <dbm>
 * over USB serial (115200). All verification happens on the hub
 * (hub/lora_gateway.py parses this format). Keep no secrets here.
 *
 * Board: any ESP32 dev module. Library: LoRa (Sandeep Mistry).
 * Wiring: SCK=18 MISO=19 MOSI=23 NSS=5 RST=14 DIO0=2 (classic ESP32 VSPI).
 */

#include <SPI.h>
#include <LoRa.h>

static const long LORA_FREQ = 433E6;
static const int  NSS = 5, RST = 14, DIO0 = 2;

void setup() {
  Serial.begin(115200);
  LoRa.setPins(NSS, RST, DIO0);
  if (!LoRa.begin(LORA_FREQ)) {
    Serial.println("ERR LoRa init failed");
    while (true) delay(1000);
  }
  LoRa.setSpreadingFactor(9);          // must match the nodes
  Serial.println("OK VanniKawachh gateway ready");
}

void loop() {
  int n = LoRa.parsePacket();
  if (n <= 0) return;
  Serial.print("RX ");
  while (LoRa.available()) {
    uint8_t b = (uint8_t)LoRa.read();
    if (b < 16) Serial.print('0');
    Serial.print(b, HEX);
  }
  Serial.print(" RSSI ");
  Serial.println(LoRa.packetRssi());
}
