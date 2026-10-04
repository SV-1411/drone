import hashlib
import hmac
import json

import pytest

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
    pending = relay.pending()
    assert len(pending) == 1
    assert relay.authenticate_pi("Bearer " + "t" * 48)
    assert not relay.authenticate_pi("Bearer wrong")
    assert relay.ack("pole-1", 7)
    assert relay.pending() == []


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
