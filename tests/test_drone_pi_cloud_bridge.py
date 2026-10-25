import time
import unittest
import tempfile
import os
from unittest.mock import patch

from scripts import drone_pi_cloud_bridge as bridge
from hub.edge_relay import EdgeRelay


def good_state():
    health = {"vehicle_connected": True, "state": "IDLE", "auth_enabled": True,
              "flight_limits": {"allow_real_dispatch": True,
                                "cruise_altitude_m": 2, "cruise_speed_ms": 0.5,
                                "max_mission_duration_s": 120,
                                "geofence_radius_m": 60}}
    telemetry = {"state": "IDLE", "armed": False, "timestamp": time.time(),
                 "gps_fix": 3, "gps_sats": 10, "battery_voltage": 12.0,
                 "battery_pct": 90, "lat": 21.145, "lon": 79.088,
                 "home_lat": 21.145, "home_lon": 79.088,
                 "home_source": "captured"}
    return health, telemetry


class DronePiBridgeTests(unittest.TestCase):
    def test_verified_queue_claim_and_result(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
                "VANNI_RELAY_DB": os.path.join(temp_dir, "relay.sqlite3"),
                "VANNI_DRONE_ESP_TOKEN": "s" * 32}):
            relay = EdgeRelay()
            self.assertTrue(relay.queue_drone_esp_incident(
                "incident-1", "sensing-pi", 21.145, 79.088, 0.8))
            command = relay.claim_drone_esp_command()
            self.assertEqual(command["id"], "incident-1")
            self.assertIsNone(relay.claim_drone_esp_command())
            self.assertTrue(relay.finish_drone_esp_command(
                "incident-1", "mission_queued", "local mission abc"))
            self.assertFalse(relay.finish_drone_esp_command(
                "incident-1", "mission_queued", "duplicate"))

    def test_valid_supervised_nearby_target(self):
        health, telemetry = good_state()
        self.assertIsNone(bridge.readiness(health, telemetry, (21.14505, 79.088)))

    def test_flight_lock_and_missing_battery_rejected(self):
        health, telemetry = good_state()
        health["flight_limits"]["allow_real_dispatch"] = False
        self.assertIn("locked", bridge.readiness(health, telemetry))
        health["flight_limits"]["allow_real_dispatch"] = True
        telemetry["battery_voltage"] = 0.032
        self.assertIn("battery", bridge.readiness(health, telemetry))

    def test_missing_gps_and_far_target_rejected(self):
        health, telemetry = good_state()
        telemetry["gps_sats"] = 0
        self.assertIn("GPS", bridge.readiness(health, telemetry))
        telemetry["gps_sats"] = 10
        self.assertIn("radius", bridge.readiness(health, telemetry, (21.146, 79.088)))

    def test_process_does_not_call_trigger_when_preflight_fails(self):
        health, telemetry = good_state()
        telemetry["gps_fix"] = 1
        with patch.object(bridge, "local_state", return_value=(health, telemetry)), \
             patch.object(bridge, "request_json") as request, \
             patch.object(bridge, "report") as report:
            bridge.process({"id": "incident-1", "lat": 21.145, "lon": 79.088})
        request.assert_not_called()
        self.assertEqual(report.call_args.args[1], "rejected")


if __name__ == "__main__":
    unittest.main()
