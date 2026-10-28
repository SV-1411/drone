"""A phone login can queue only real, model-verified audio with precise GPS."""
import base64
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from hub.edge_relay import EdgeRelay
from hub import webapp


class PhoneQueueTests(unittest.TestCase):
    def test_phone_basic_login(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "VANNI_RELAY_DB": str(Path(directory) / "relay.db"),
                "VANNI_PHONE_USER": "node-operator",
                "VANNI_PHONE_PASSWORD": "a-strong-test-password-at-least-24-chars"}):
            relay = EdgeRelay()
        good = base64.b64encode(
            b"node-operator:a-strong-test-password-at-least-24-chars").decode()
        self.assertTrue(relay.phone_auth_configured())
        self.assertTrue(relay.authenticate_phone("Basic " + good))
        self.assertFalse(relay.authenticate_phone("Basic " + base64.b64encode(
            b"node-operator:wrong-password").decode()))

    def test_only_verified_audio_with_precise_gps_is_queued(self):
        incident = SimpleNamespace(dispatched=True, distress_confirmed=True,
                                   verifier_backend="YAMNet (AudioSet fallback)",
                                   mission_id="test-incident", audio_score=0.9)
        with patch.object(webapp.edge_relay, "queue_drone_esp_incident", return_value=True) as queue:
            self.assertFalse(webapp._queue_authenticated_audio(
                incident, 21.1, 79.1, 5, False, "phone",
                sensing_signed=False, phone_logged_in=False))
            self.assertFalse(webapp._queue_authenticated_audio(
                incident, 21.1, 79.1, 100, False, "phone",
                sensing_signed=False, phone_logged_in=True))
            self.assertFalse(webapp._queue_authenticated_audio(
                incident, 21.1, 79.1, 5, True, "phone",
                sensing_signed=False, phone_logged_in=True))
            incident.verifier_backend = "prosodic stressed-speech verifier"
            self.assertFalse(webapp._queue_authenticated_audio(
                incident, 21.1, 79.1, 5, False, "phone",
                sensing_signed=False, phone_logged_in=True))
            queue.assert_not_called()
            incident.verifier_backend = "YAMNet (AudioSet fallback)"
            self.assertTrue(webapp._queue_authenticated_audio(
                incident, 21.1, 79.1, 5, False, "phone",
                sensing_signed=False, phone_logged_in=True))
            queue.assert_called_once()

    def test_node_page_and_simulation_are_login_protected(self):
        with patch.object(webapp.edge_relay, "phone_user", "node-operator"), \
             patch.object(webapp.edge_relay, "phone_password",
                          "a-strong-test-password-at-least-24-chars"):
            client = TestClient(webapp.app)
            self.assertEqual(client.get("/node").status_code, 401)
            self.assertEqual(client.post("/demo-dispatch?lat=21.1&lon=79.1").status_code, 401)
            self.assertEqual(client.post("/operator/simulate-distress", json={
                "lat": 21.1, "lon": 79.1, "accuracy_m": 5}).status_code, 401)
            self.assertEqual(client.get("/node", auth=(
                "node-operator", "a-strong-test-password-at-least-24-chars")).status_code, 200)

    def test_authenticated_operator_test_enters_same_pi_queue(self):
        auth = ("node-operator", "a-strong-test-password-at-least-24-chars")
        ready = {"connected": True, "armed": False, "mission_state": "IDLE",
                 "gps_fix": 3, "satellites": 9}
        with patch.object(webapp.edge_relay, "phone_user", auth[0]), \
             patch.object(webapp.edge_relay, "phone_password", auth[1]), \
             patch.object(webapp.edge_relay, "ready", return_value=True), \
             patch.object(webapp.edge_relay, "drone_esp_status", return_value=ready), \
             patch.object(webapp.edge_relay, "queue_drone_esp_incident", return_value=True) as queue:
            client = TestClient(webapp.app)
            response = client.post("/operator/simulate-distress", auth=auth, json={
                "lat": 21.145, "lon": 79.088, "accuracy_m": 5})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "pending_pi_safety_checks")
            self.assertEqual(queue.call_args.args[1:],
                             ("operator-test", 21.145, 79.088, 1.0))
            bad_gps = client.post("/operator/simulate-distress", auth=auth, json={
                "lat": 21.145, "lon": 79.088, "accuracy_m": 60})
            self.assertEqual(bad_gps.status_code, 400)
            self.assertEqual(queue.call_count, 1)

    def test_operator_test_rejects_offline_pi(self):
        auth = ("node-operator", "a-strong-test-password-at-least-24-chars")
        with patch.object(webapp.edge_relay, "phone_user", auth[0]), \
             patch.object(webapp.edge_relay, "phone_password", auth[1]), \
             patch.object(webapp.edge_relay, "ready", return_value=True), \
             patch.object(webapp.edge_relay, "drone_esp_status", return_value={
                 "connected": False, "armed": False, "mission_state": "IDLE",
                 "gps_fix": 3, "satellites": 9}), \
             patch.object(webapp.edge_relay, "queue_drone_esp_incident") as queue:
            response = TestClient(webapp.app).post(
                "/operator/simulate-distress", auth=auth,
                json={"lat": 21.145, "lon": 79.088, "accuracy_m": 5})
            self.assertEqual(response.status_code, 503)
            queue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
