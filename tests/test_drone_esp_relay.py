"""Software checks for the drone ESP's cloud command exchange.

These do not substitute for a wired MAVLink heartbeat or a flight test.
"""

from hub.edge_relay import EdgeRelay


def test_drone_esp_claim_and_result(tmp_path, monkeypatch):
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    monkeypatch.setenv("VANNI_DRONE_ESP_TOKEN", "t" * 32)
    relay = EdgeRelay()

    assert not relay.authenticate_drone_esp("Bearer wrong")
    assert relay.authenticate_drone_esp("Bearer " + "t" * 32)
    assert relay.queue_drone_esp_incident("incident-1", "sensing-pi", 21.0, 79.0, 0.9)
    assert not relay.queue_drone_esp_incident("incident-2", "sensing-pi", 21.0, 79.0, 0.9)

    command = relay.claim_drone_esp_command()
    assert command == {"id": "incident-1", "node_id": "sensing-pi",
                       "lat": 21.0, "lon": 79.0, "score": 0.9}
    assert relay.claim_drone_esp_command() is None
    assert relay.finish_drone_esp_command("incident-1", "mission_uploaded",
                                          "Pixhawk accepted mission")
    assert not relay.finish_drone_esp_command("incident-1", "mission_uploaded", "duplicate")
    assert relay.drone_esp_status()["last_command"]["status"] == "mission_uploaded"
    assert relay.drone_esp_status()["last_command"]["lat"] == 21.0


def test_drone_esp_telemetry_status(tmp_path, monkeypatch):
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    relay = EdgeRelay()
    assert relay.drone_esp_status()["connected"] is False
    relay.record_drone_esp_telemetry(True, 3, 8, False, "idle")
    status = relay.drone_esp_status()
    assert status["connected"] is True
    assert status["gps_fix"] == 3
    assert status["satellites"] == 8
    assert status["armed"] is False
