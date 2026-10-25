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
            self.assertEqual(client.get("/node", auth=(
                "node-operator", "a-strong-test-password-at-least-24-chars")).status_code, 200)


if __name__ == "__main__":
    unittest.main()
