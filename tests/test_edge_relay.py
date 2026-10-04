import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from hub.edge_relay import EdgeRelay


def test_signed_alert_queue_dedupe_poll_and_ack(tmp_path, monkeypatch):
    key = bytes(range(32))
    monkeypatch.setenv("VANNI_ALERT_KEY", key.hex())
    monkeypatch.setenv("VANNI_RELAY_PI_TOKEN", "t" * 48)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    relay = EdgeRelay()
    event = {"node_id": "pole-1", "seq": 7, "kind": "sound_level_candidate",
             "lat": 21.1234567, "lon": 79.1234567, "sound_score": 0.8}
    body = json.dumps(event).encode()
    signature = hmac.new(key, body, hashlib.sha256).hexdigest()

    assert relay.ready()
    assert relay.enqueue(body, signature)[0] == "queued"
    assert relay.enqueue(body, signature)[0] == "duplicate"
    recent = relay.recent()
    assert len(recent) == 1
    assert recent[0]["node_id"] == "pole-1"
    assert recent[0]["sound_score"] == 0.8
    assert recent[0]["pi_received"] is False
    assert "signature" not in recent[0]
    assert "body_b64" not in recent[0]
    pending = relay.pending()
    assert len(pending) == 1
    assert relay.authenticate_pi("Bearer " + "t" * 48)
    assert not relay.authenticate_pi("Bearer wrong")
    assert relay.ack("pole-1", 7)
    assert relay.pending() == []
    assert relay.recent()[0]["pi_received"] is True


def test_reject_invalid_signature_and_alert_values(tmp_path, monkeypatch):
    monkeypatch.setenv("VANNI_ALERT_KEY", bytes(range(32)).hex())
    monkeypatch.setenv("VANNI_RELAY_PI_TOKEN", "t" * 48)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    relay = EdgeRelay()
    body = json.dumps({"node_id": "pole-1", "seq": 1,
                       "kind": "sound_level_candidate", "lat": 91,
                       "lon": 0, "sound_score": 0.9}).encode()
    with pytest.raises(PermissionError):
        relay.enqueue(body, "0" * 64)
    signature = hmac.new(bytes(range(32)), body, hashlib.sha256).hexdigest()
    with pytest.raises(ValueError, match="invalid event values"):
        relay.enqueue(body, signature)


def test_operator_real_command_is_at_most_once_and_uses_signed_node(tmp_path, monkeypatch):
    key = bytes(range(32))
    monkeypatch.setenv("VANNI_ALERT_KEY", key.hex())
    monkeypatch.setenv("VANNI_RELAY_PI_TOKEN", "t" * 48)
    monkeypatch.setenv("VANNI_OPERATOR_KEY", "o" * 48)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    relay = EdgeRelay()
    assert relay.authenticate_operator("o" * 48)
    assert not relay.authenticate_operator("wrong")
    with pytest.raises(ValueError, match="no recent"):
        relay.queue_real_test()
    event = {"node_id": "pole-1", "seq": 1, "kind": "sound_level_candidate",
             "lat": 21.1234567, "lon": 79.1234567, "sound_score": 0.8}
    body = json.dumps(event).encode()
    relay.enqueue(body, hmac.new(key, body, hashlib.sha256).hexdigest())
    queued = relay.queue_real_test()
    assert queued["target"] == [event["lat"], event["lon"]]
    with pytest.raises(ValueError, match="already in progress"):
        relay.queue_real_test()
    claimed = relay.claim_real_test()
    assert claimed["id"] == queued["id"]
    assert relay.claim_real_test() is None
    assert relay.finish_real_test(claimed["id"], "rejected", "GPS unavailable")
    assert relay.real_test_status(claimed["id"])["detail"] == "GPS unavailable"


def test_web_real_test_requires_operator_key(tmp_path, monkeypatch):
    from hub import webapp
    key = bytes(range(32))
    monkeypatch.setenv("VANNI_ALERT_KEY", key.hex())
    monkeypatch.setenv("VANNI_RELAY_PI_TOKEN", "t" * 48)
    monkeypatch.setenv("VANNI_OPERATOR_KEY", "o" * 48)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    relay = EdgeRelay()
    monkeypatch.setattr(webapp, "edge_relay", relay)
    unauthorized = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as denied:
        webapp.edge_real_test(unauthorized)
    assert denied.value.status_code == 401
    assert "edge-real-button" in webapp.dashboard()
