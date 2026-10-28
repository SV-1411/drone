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
                 "home_source": "captured", "home_captured_at": time.time()}
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

    def test_saved_home_cannot_be_used_for_new_launch(self):
        health, telemetry = good_state()
        telemetry["home_captured_at"] = time.time() - 600
        self.assertIn("stale", bridge.readiness(health, telemetry))
        self.assertIsNone(bridge.readiness(health, telemetry, check_home=False))
        telemetry["home_captured_at"] = time.time()
        telemetry["home_lat"] = 21.1452
        self.assertIn("moved", bridge.readiness(health, telemetry))

    def test_process_does_not_call_trigger_when_preflight_fails(self):
        health, telemetry = good_state()
        telemetry["gps_fix"] = 1
        with patch.object(bridge, "local_state", return_value=(health, telemetry)), \
             patch.object(bridge, "request_json") as request, \
             patch.object(bridge, "report") as report:
            bridge.process({"id": "incident-1", "lat": 21.145, "lon": 79.088})
        request.assert_not_called()
        self.assertEqual(report.call_args.args[1], "rejected")

    def test_operator_test_is_not_labelled_verified_audio(self):
        health, telemetry = good_state()
        with patch.object(bridge, "local_state", return_value=(health, telemetry)), \
             patch.object(bridge, "request_json", return_value={
                 "status": "queued", "mission_id": "mission-1"}) as request, \
             patch.object(bridge, "report") as report:
            bridge.process({"id": "operator-test-1", "node_id": "operator-test",
                            "lat": 21.14505, "lon": 79.088})
        self.assertEqual(request.call_args.kwargs["payload"]["incident_type"],
                         "operator_test")
        self.assertEqual(report.call_args.args[1], "mission_queued")

    def test_cloud_command_reaches_local_mission_request_without_flight(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
                "VANNI_RELAY_DB": os.path.join(temp_dir, "relay.sqlite3")}):
            relay = EdgeRelay()
            self.assertTrue(relay.queue_drone_esp_incident(
                "operator-test-e2e", "operator-test", 21.14505, 79.088, 1.0))
            command = relay.claim_drone_esp_command()
            health, telemetry = good_state()
            with patch.object(bridge, "local_state", return_value=(health, telemetry)), \
                 patch.object(bridge, "request_json", return_value={
                     "status": "queued", "mission_id": "mission-e2e"}) as request, \
                 patch.object(bridge, "report") as report:
                bridge.process(command)
            self.assertEqual(request.call_args.args[0], bridge.API_URL + "/trigger")
            self.assertEqual(request.call_args.kwargs["payload"]["lat"], 21.14505)
            self.assertEqual(request.call_args.kwargs["payload"]["lon"], 79.088)
            self.assertEqual(report.call_args.args[1], "mission_queued")


if __name__ == "__main__":
    unittest.main()
