import hashlib
import hmac
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.wifi_alert_receiver import (
    AlertServer, load_nodes, process_real_test, real_flight_preflight, validate_alert,
)


KEY = bytes(range(32))
NODES = {"pole-1": (21.1234567, 79.1234567)}


def signed_event(**changes):
    event = {"node_id": "pole-1", "seq": 1,
             "kind": "sound_level_candidate", "lat": 21.1234567,
             "lon": 79.1234567, "sound_score": 0.8}
    event.update(changes)
    body = json.dumps(event).encode()
    signature = hmac.new(KEY, body, hashlib.sha256).hexdigest()
    return body, signature


def test_accept_and_reject_replay():
    body, signature = signed_event()
    assert validate_alert(body, signature, KEY, NODES, {})["lat"] == 21.1234567
    with pytest.raises(ValueError, match="stale"):
        validate_alert(body, signature, KEY, NODES, {"pole-1": 1})


def test_reject_bad_signature_and_forged_location():
    body, signature = signed_event(lat=22.0)
    with pytest.raises(PermissionError):
        validate_alert(body, "0" * 64, KEY, NODES, {})
    with pytest.raises(ValueError, match="coordinates"):
        validate_alert(body, signature, KEY, NODES, {})


def test_reject_wrong_kind_and_unregistered_node():
    for change, match in [({"kind": "confirmed_distress"}, "kind"),
                          ({"node_id": "other"}, "unknown")]:
        body, signature = signed_event(**change)
        with pytest.raises(ValueError, match=match):
            validate_alert(body, signature, KEY, NODES, {})


def test_load_registry(tmp_path: Path):
    path = tmp_path / "nodes.json"
    path.write_text('{"pole-1":{"lat":21.1234567,"lon":79.1234567}}')
    assert load_nodes(path) == NODES


def test_real_test_remains_locked_without_local_enablement():
    command = {"lat": 21.1234567, "lon": 79.1234567}
    assert process_real_test(command, "http://127.0.0.1:8000", "x" * 48,
                             False, True, 1000) == (
        "rejected", "real flight mode is locked on the Pi")


def test_real_preflight_rejects_missing_gps_battery_and_remote_target():
    good = {"state": "IDLE", "mission_id": None, "armed": False,
            "gps_fix": 3, "gps_sats": 10, "battery_pct": 80,
            "battery_voltage": 12.1, "lat": 21.1234, "lon": 79.1234}
    assert real_flight_preflight(good, 21.1235, 79.1235, 1000) is None
    assert "GPS" in real_flight_preflight({**good, "gps_fix": 1},
                                          21.1235, 79.1235, 1000)
    assert "battery" in real_flight_preflight({**good, "battery_pct": None},
                                              21.1235, 79.1235, 1000)
    assert "radius" in real_flight_preflight(good, 22.0, 79.1235, 1000)


def test_http_receiver_persists_and_rejects_replay(tmp_path: Path):
    database = tmp_path / "alerts.sqlite3"
    server = AlertServer(("127.0.0.1", 0), KEY, NODES, database)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body, signature = signed_event()
        request = Request(f"http://127.0.0.1:{server.server_port}/alert", body,
                          headers={"X-Alert-Signature": signature}, method="POST")
        with urlopen(request, timeout=2) as response:
            payload = json.load(response)
        assert payload == {"accepted": True, "dispatch": "LOCKED_BENCH_ONLY"}
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == 400
        assert database.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
