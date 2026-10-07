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


def test_operator_bench_command_needs_no_node_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("VANNI_ALERT_KEY", bytes(range(32)).hex())
    monkeypatch.setenv("VANNI_RELAY_PI_TOKEN", "t" * 48)
    monkeypatch.setenv("VANNI_OPERATOR_KEY", "o" * 48)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    relay = EdgeRelay()
    request = relay.queue_props_off_bench_test()
    claimed = relay.claim_real_test()
    assert claimed["id"] == request["id"]
    assert claimed["node_id"] == "operator-bench"
    assert relay.finish_real_test(claimed["id"], "completed", "disarmed")
    assert relay.real_test_status(claimed["id"])["status"] == "completed"


def test_audio_verification_is_visible_on_latest_alert(tmp_path, monkeypatch):
    key = bytes(range(32))
    monkeypatch.setenv("VANNI_ALERT_KEY", key.hex())
    monkeypatch.setenv("VANNI_RELAY_PI_TOKEN", "t" * 48)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    relay = EdgeRelay()
    event = {"node_id": "pole-1", "seq": 4, "kind": "sound_level_candidate",
             "lat": 21.1234567, "lon": 79.1234567, "sound_score": 0.8}
    body = json.dumps(event).encode()
    relay.enqueue(body, hmac.new(key, body, hashlib.sha256).hexdigest())
    assert relay.record_verification("pole-1", 4, True, "YAMNet", 0.91)
    latest = relay.recent(1)[0]
    assert latest["audio_received"] is True
    assert latest["audio_confirmed"] is True
    assert latest["audio_backend"] == "YAMNet"


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
    assert "Simulate distress (real test)" in webapp.dashboard()
    authorized = Request({"type": "http", "headers":
                          [(b"x-operator-key", b"o" * 48)]})
    assert webapp.edge_bench_test(authorized)["kind"] == "props_off_bench"


def test_public_phone_report_needs_verified_voice_and_operator_for_flight(tmp_path, monkeypatch):
    import asyncio
    from hub import webapp

    monkeypatch.setenv("VANNI_ALERT_KEY", bytes(range(32)).hex())
    monkeypatch.setenv("VANNI_RELAY_PI_TOKEN", "t" * 48)
    monkeypatch.setenv("VANNI_OPERATOR_KEY", "o" * 48)
    monkeypatch.setenv("VANNI_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    relay = EdgeRelay()
    monkeypatch.setattr(webapp, "edge_relay", relay)
    class PhoneRequest:
        async def json(self):
            return {"lat": 21.10512, "lon": 79.00352, "accuracy_m": 12}

    button = asyncio.run(webapp.mobile_report(PhoneRequest()))
    button_id = button["id"]
    assert relay.recent_mobile(1)[0]["source"] == "button"
    authorized = Request({"type": "http", "headers":
                          [(b"x-operator-key", b"o" * 48)]})
    with pytest.raises(HTTPException) as button_denied:
        webapp.approve_mobile_incident(button_id, authorized)
    assert button_denied.value.status_code == 409
    assert relay.claim_real_test() is None

    voice = relay.record_mobile_incident(21.10512, 79.00352, 12,
                                         "voice", True, 0.88)
    unauthorized = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as missing_key:
        webapp.approve_mobile_incident(voice["id"], unauthorized)
    assert missing_key.value.status_code == 401
    approved = webapp.approve_mobile_incident(voice["id"], authorized)
    assert approved["status"] == "pending"
    command = relay.claim_real_test()
    assert command["lat"] == 21.10512
    assert command["lon"] == 79.00352
    assert command["node_id"].startswith("phone-")
    with pytest.raises(HTTPException) as duplicate:
        webapp.approve_mobile_incident(voice["id"], authorized)
    assert duplicate.value.status_code == 409
