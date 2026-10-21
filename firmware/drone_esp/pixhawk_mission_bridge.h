#pragma once

// Install the official MAVLink C headers (mavlink/c_library_v2) as an Arduino
// library with an MAVLink.h wrapper. TELEM2 is a 3.3 V UART.
#include <MAVLink.h>
#include <HardwareSerial.h>
#include <math.h>

class PixhawkMissionBridge {
 public:
  enum Outcome { NONE, UPLOADED, REJECTED, FAILED };
  // Dedicated pins avoid the board's USB-to-UART chip on GPIO43/GPIO44.
  static constexpr int TX_PIN = 17;  // ESP TX -> Pixhawk TELEM2 RX (pin 3)
  static constexpr int RX_PIN = 18;  // ESP RX <- Pixhawk TELEM2 TX (pin 2)
  static constexpr int BAUD = 57600; // SERIAL2_BAUD=57 in the saved params
  static constexpr uint8_t SOURCE_COMPONENT = 190; // GCS-style mission uploader

  void begin() {
    // TLS requests can block for several seconds. Keep incoming telemetry in
    // the UART ring until loop() resumes instead of losing MAVLink frames.
    uart_.setRxBufferSize(32768);
    uart_.begin(BAUD, SERIAL_8N1, RX_PIN, TX_PIN);
    Serial.println("MAVLink UART ready; mission upload only, no arm/start");
  }

  bool queueDistress(double lat, double lon) {
    if (!validCoordinates(lat, lon) || pending_ || uploading_) return false;
    outcome_ = NONE;
    targetLat_ = lat;
    targetLon_ = lon;
    pending_ = true;
    queuedAt_ = millis();
    Serial.printf("MAVLink mission queued: %.7f,%.7f\n", lat, lon);
    return true;
  }

  void tick() {
    mavlink_message_t message;
    mavlink_status_t status;
    while (uart_.available()) {
      if (mavlink_parse_char(MAVLINK_COMM_1, uart_.read(), &message, &status))
        handle(message);
    }
    const uint32_t now = millis();
    if (now - lastGcsHeartbeat_ >= 1000) {
      lastGcsHeartbeat_ = now;
      mavlink_heartbeat_t heartbeat = {};
      heartbeat.type = MAV_TYPE_GCS;
      heartbeat.autopilot = MAV_AUTOPILOT_INVALID;
      heartbeat.system_status = MAV_STATE_ACTIVE;
      mavlink_msg_heartbeat_encode(253, SOURCE_COMPONENT,
                                   &message, &heartbeat);
      send(message);
    }
    if (uploading_ && now - lastProgress_ > 6000) {
      uploading_ = false;
      pending_ = false;
      outcome_ = FAILED;
      outcomeDetail_ = "mission upload timed out";
      Serial.println("MAVLink mission upload timed out; flight not started");
    }
    if (pending_ && !uploading_ && now - queuedAt_ > 30000) {
      pending_ = false;
      outcome_ = REJECTED;
      outcomeDetail_ = "Pixhawk GPS, position, or heartbeat not ready";
      Serial.println("MAVLink mission expired: no fresh disarmed GPS-ready Pixhawk");
    }
    if (pending_ && !uploading_) startUpload(now);
  }

  void printStatus() const {
    const uint32_t now = millis();
    Serial.printf("Pixhawk link=%s GPS_fix=%u sats=%u position=%s armed=%d mission=%s\n",
                  autopilotSystem_ && now - lastHeartbeat_ <= 3000 ? "fresh" : "missing",
                  gpsFix_, satellites_,
                  havePosition_ && now - lastPosition_ <= 3000 ? "fresh" : "missing",
                  armed_, uploading_ ? "uploading" : (pending_ ? "queued" : "idle"));
  }

  bool heartbeatFresh() const {
    return autopilotSystem_ && millis() - lastHeartbeat_ <= 3000;
  }
  uint8_t gpsFix() const { return gpsFix_; }
  uint8_t satellites() const { return satellites_; }
  bool armed() const { return armed_; }
  const char* missionState() const {
    return uploading_ ? "uploading" : (pending_ ? "queued" : "idle");
  }
  Outcome takeOutcome(String& detail) {
    Outcome result = outcome_;
    detail = outcomeDetail_;
    outcome_ = NONE;
    outcomeDetail_ = "";
    return result;
  }

 private:
  HardwareSerial uart_{1};
  bool pending_ = false;
  bool uploading_ = false;
  bool havePosition_ = false;
  bool armed_ = false;
  Outcome outcome_ = NONE;
  String outcomeDetail_;
  uint8_t autopilotSystem_ = 0;
  uint8_t autopilotComponent_ = 0;
  uint8_t gpsFix_ = 0;
  uint8_t satellites_ = 0;
  uint32_t lastHeartbeat_ = 0;
  uint32_t lastPosition_ = 0;
  uint32_t lastGps_ = 0;
  uint32_t lastGcsHeartbeat_ = 0;
  uint32_t lastProgress_ = 0;
  uint32_t queuedAt_ = 0;
  int32_t currentLatE7_ = 0;
  int32_t currentLonE7_ = 0;
  double targetLat_ = 0;
  double targetLon_ = 0;

  static bool validCoordinates(double lat, double lon) {
    return isfinite(lat) && isfinite(lon) && lat >= -90 && lat <= 90 &&
           lon >= -180 && lon <= 180 && (lat != 0 || lon != 0);
  }

  static double distanceMetres(double lat1, double lon1,
                               double lat2, double lon2) {
    constexpr double radians = 0.017453292519943295;
    const double dLat = (lat2 - lat1) * radians;
    const double dLon = (lon2 - lon1) * radians;
    const double a = pow(sin(dLat / 2), 2) + cos(lat1 * radians) *
                     cos(lat2 * radians) * pow(sin(dLon / 2), 2);
    return 12742000.0 * asin(sqrt(fmin(1.0, a)));
  }

  void send(const mavlink_message_t& message) {
    uint8_t buffer[MAVLINK_MAX_PACKET_LEN];
    const uint16_t length = mavlink_msg_to_send_buffer(buffer, &message);
    uart_.write(buffer, length);
  }

  void startUpload(uint32_t now) {
    if (!autopilotSystem_ || now - lastHeartbeat_ > 3000 ||
        !havePosition_ || now - lastPosition_ > 3000 ||
        now - lastGps_ > 3000 || gpsFix_ < 3 || satellites_ < 6 || armed_)
      return;
    const double distance = distanceMetres(currentLatE7_ / 1e7,
                                           currentLonE7_ / 1e7,
                                           targetLat_, targetLon_);
    if (distance > 30.0) {
      Serial.printf("MAVLink target rejected: %.1f m exceeds 30 m bench limit\n",
                    distance);
      pending_ = false;
      outcome_ = REJECTED;
      outcomeDetail_ = "target exceeds 30 m from Pixhawk GPS";
      return;
    }
    mavlink_mission_count_t count = {};
    count.target_system = autopilotSystem_;
    count.target_component = autopilotComponent_;
    count.count = 3;
    count.mission_type = MAV_MISSION_TYPE_MISSION;
    mavlink_message_t message;
    mavlink_msg_mission_count_encode(253, SOURCE_COMPONENT,
                                     &message, &count);
    send(message);
    uploading_ = true;
    lastProgress_ = now;
    Serial.printf("MAVLink mission count sent (3 items, target %.1f m)\n", distance);
  }

  void sendItem(uint16_t seq) {
    mavlink_mission_item_int_t item = {};
    item.target_system = autopilotSystem_;
    item.target_component = autopilotComponent_;
    item.seq = seq;
    item.frame = MAV_FRAME_GLOBAL_RELATIVE_ALT_INT;
    item.current = seq == 0 ? 1 : 0;
    item.autocontinue = 1;
    item.mission_type = MAV_MISSION_TYPE_MISSION;
    item.z = 3.0f; // conservative takeoff/waypoint height for a future field test
    if (seq == 0) {
      item.command = MAV_CMD_NAV_TAKEOFF;
      item.x = currentLatE7_;
      item.y = currentLonE7_;
    } else if (seq == 1) {
      item.command = MAV_CMD_NAV_WAYPOINT;
      item.x = (int32_t)llround(targetLat_ * 1e7);
      item.y = (int32_t)llround(targetLon_ * 1e7);
      item.param1 = 2.0f; // short hold at destination
    } else {
      item.command = MAV_CMD_NAV_RETURN_TO_LAUNCH;
      item.x = 0;
      item.y = 0;
      item.z = 0;
    }
    mavlink_message_t message;
    mavlink_msg_mission_item_int_encode(253, SOURCE_COMPONENT,
                                        &message, &item);
    send(message);
    lastProgress_ = millis();
    Serial.printf("MAVLink mission item %u sent\n", seq);
  }

  void handle(const mavlink_message_t& message) {
    if (message.msgid == MAVLINK_MSG_ID_HEARTBEAT) {
      mavlink_heartbeat_t heartbeat;
      mavlink_msg_heartbeat_decode(&message, &heartbeat);
      if (heartbeat.autopilot != MAV_AUTOPILOT_ARDUPILOTMEGA) return;
      autopilotSystem_ = message.sysid;
      autopilotComponent_ = message.compid;
      armed_ = (heartbeat.base_mode & MAV_MODE_FLAG_SAFETY_ARMED) != 0;
      lastHeartbeat_ = millis();
      return;
    }
    if (!autopilotSystem_ || message.sysid != autopilotSystem_) return;
    if (message.msgid == MAVLINK_MSG_ID_GPS_RAW_INT) {
      mavlink_gps_raw_int_t gps;
      mavlink_msg_gps_raw_int_decode(&message, &gps);
      gpsFix_ = gps.fix_type;
      satellites_ = gps.satellites_visible;
      lastGps_ = millis();
    } else if (message.msgid == MAVLINK_MSG_ID_GLOBAL_POSITION_INT) {
      mavlink_global_position_int_t position;
      mavlink_msg_global_position_int_decode(&message, &position);
      currentLatE7_ = position.lat;
      currentLonE7_ = position.lon;
      havePosition_ = currentLatE7_ || currentLonE7_;
      lastPosition_ = millis();
    } else if (uploading_ && message.msgid == MAVLINK_MSG_ID_MISSION_REQUEST_INT) {
      mavlink_mission_request_int_t request;
      mavlink_msg_mission_request_int_decode(&message, &request);
      if (request.target_system == 253 &&
          request.mission_type == MAV_MISSION_TYPE_MISSION && request.seq < 3)
        sendItem(request.seq);
    } else if (uploading_ && message.msgid == MAVLINK_MSG_ID_MISSION_ACK) {
      mavlink_mission_ack_t ack;
      mavlink_msg_mission_ack_decode(&message, &ack);
      if (ack.target_system != 253 || ack.mission_type != MAV_MISSION_TYPE_MISSION)
        return;
      Serial.printf("MAVLink mission ACK=%u (%s); motors remain disarmed\n",
                    ack.type, ack.type == MAV_MISSION_ACCEPTED ? "accepted" : "rejected");
      uploading_ = false;
      pending_ = false;
      outcome_ = ack.type == MAV_MISSION_ACCEPTED ? UPLOADED : REJECTED;
      outcomeDetail_ = ack.type == MAV_MISSION_ACCEPTED
          ? "Pixhawk accepted mission" : "Pixhawk rejected mission";
    }
  }
};
