"""The embedded consumer must be able to independently reject stale commands."""
import pytest

from hub.edge_relay import EdgeRelay


@pytest.fixture
def relay(tmp_path, monkeypatch):
    monkeypatch.setenv("VANNI_ALERT_KEY", bytes(range(32)).hex())
    monkeypatch.setenv("VANNI_RELAY_PI_TOKEN", "device-token-" * 4)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    return EdgeRelay()


def test_claim_exposes_original_expiry_and_cannot_replay(relay, monkeypatch):
    monkeypatch.setattr("hub.edge_relay.time.time", lambda: 1000.0)
    voice = relay.record_mobile_incident(21.1, 79.1, 10, "voice", True, .9)
    approved = relay.queue_mobile_real_test(voice["id"])
    monkeypatch.setattr("hub.edge_relay.time.time", lambda: 1049.0)
    claimed = relay.claim_real_test()
    assert claimed["id"] == approved["id"]
    assert claimed["created"] == 1000.0
    assert claimed["expires_at"] == 1060.0
    assert claimed["node_id"].startswith("phone-")
    assert claimed["lat"] == 21.1
    assert relay.claim_real_test() is None


def test_expired_approval_never_reaches_device(relay, monkeypatch):
    monkeypatch.setattr("hub.edge_relay.time.time", lambda: 1000.0)
    voice = relay.record_mobile_incident(21.1, 79.1, 10, "voice", True, .9)
    approved = relay.queue_mobile_real_test(voice["id"])
    monkeypatch.setattr("hub.edge_relay.time.time", lambda: 1061.0)
    assert relay.claim_real_test() is None
    assert relay.real_test_status(approved["id"])["status"] == "expired"


def test_operator_key_alone_supports_esp_and_keeps_queue_private(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request
    from hub import webapp

    monkeypatch.delenv("VANNI_RELAY_PI_TOKEN", raising=False)
    monkeypatch.delenv("VANNI_ALERT_KEY", raising=False)
    monkeypatch.setenv("VANNI_OPERATOR_KEY", "o" * 48)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "operator-only.sqlite3"))
    relay = EdgeRelay()
    monkeypatch.setattr(webapp, "edge_relay", relay)
    assert relay.ready()
    denied = Request({"type": "http", "headers": []})
    for handler in (webapp.edge_real_test_claim, webapp.edge_device_status):
        with pytest.raises(HTTPException) as error:
            handler(denied)
        assert error.value.status_code == 401
    request = Request({"type": "http", "headers": [(b"x-operator-key", b"o" * 48)]})
    voice = relay.record_mobile_incident(21.1, 79.1, 10, "voice", True, .9)
    command = relay.queue_mobile_real_test(voice["id"])
    assert webapp.edge_device_status(request)["authenticated"] is True
    assert webapp.edge_real_test_claim(request)["command"]["id"] == command["id"]
    assert relay.authenticate_device("", "o" * 48)
    assert not relay.authenticate_device("", "")
    with pytest.raises(PermissionError, match="not configured"):
        relay.enqueue(b"{}", "0" * 64)
