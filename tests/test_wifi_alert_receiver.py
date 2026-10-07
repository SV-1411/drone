import hashlib
import hmac
import json
import sqlite3
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.wifi_alert_receiver import (
    AlertServer, load_nodes, maybe_trigger_one_bench_check, process_real_test,
    real_flight_preflight, validate_alert,
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


def test_unmonitored_battery_prototype_still_requires_nearby_home_gps_and_target():
    good = {"state": "IDLE", "mission_id": None, "armed": False,
            "gps_fix": 3, "gps_sats": 10, "battery_pct": None,
            "battery_voltage": 0.0, "lat": 21.1234, "lon": 79.1234,
            "home_lat": 21.1234, "home_lon": 79.1234}
    assert real_flight_preflight(good, 21.1235, 79.1235, 1000, True) is None
    assert "battery" in real_flight_preflight(good, 21.1235, 79.1235, 1000)
    assert "GPS" in real_flight_preflight({**good, "gps_sats": 0},
                                         21.1235, 79.1235, 1000, True)
    assert "battery" in real_flight_preflight({**good, "battery_pct": 20},
                                             21.1235, 79.1235, 1000, True)
    assert "home" in real_flight_preflight({**good, "home_lat": 28.6139},
                                          21.1235, 79.1235, 1000, True)
    assert "radius" in real_flight_preflight(good, 21.1240, 79.1234,
                                            1000, True)


def test_unmonitored_battery_requires_local_flight_limits(monkeypatch):
    from io import BytesIO
    import scripts.wifi_alert_receiver as receiver

    class Response(BytesIO):
        def __enter__(self): return self
        def __exit__(self, *_): self.close()

    telemetry = {"state": "IDLE", "mission_id": None, "armed": False,
                 "gps_fix": 3, "gps_sats": 10, "battery_pct": None,
                 "battery_voltage": 0.0, "lat": 21.1234, "lon": 79.1234,
                 "home_lat": 21.1234, "home_lon": 79.1234}
    calls = []
    def fake_urlopen(request, timeout):
        url = request if isinstance(request, str) else request.full_url
        calls.append(url)
        if url.endswith("/telemetry"):
            return Response(json.dumps(telemetry).encode())
        if url.endswith("/health"):
            return Response(json.dumps({"flight_limits": {
                "allow_real_dispatch": True,
                "max_mission_duration_s": 120,
                "geofence_radius_m": 60}}).encode())
        assert url.endswith("/trigger")
        payload = json.loads(request.data)
        assert payload["altitude_m"] == 3
        assert payload["hover_s"] == 0
        assert payload["deliver_kit"] is False
        return Response(b'{"status":"queued","mission_id":"m1"}')
    monkeypatch.setattr(receiver, "urlopen", fake_urlopen)
    command = {"lat": 21.1235, "lon": 79.1235}
    assert process_real_test(command, "http://local", "x" * 48,
                             True, True, 1000, True) == ("queued", "mission m1")
    assert calls == ["http://local/telemetry", "http://local/health",
                     "http://local/trigger"]

    def unsafe_limits(request, timeout):
        url = request if isinstance(request, str) else request.full_url
        if url.endswith("/telemetry"):
            return Response(json.dumps(telemetry).encode())
        return Response(b'{"flight_limits":{"allow_real_dispatch":true,"max_mission_duration_s":1800,"geofence_radius_m":5000}}')
    monkeypatch.setattr(receiver, "urlopen", unsafe_limits)
    assert "limits" in process_real_test(command, "http://local", "x" * 48,
                                         True, True, 1000, True)[1]


def test_link_diagnostic_reads_pixhawk_but_never_sends_a_command(monkeypatch):
    from io import BytesIO
    import scripts.wifi_alert_receiver as receiver

    class Response(BytesIO):
        def __enter__(self): return self
        def __exit__(self, *_): self.close()

    calls = []
    def fake_urlopen(request, timeout):
        assert isinstance(request, str), "diagnostic must only perform GET requests"
        calls.append(request)
        if request.endswith("/health"):
            return Response(b'{"vehicle_connected":true,"flight_limits":{"allow_real_dispatch":false}}')
        if request.endswith("/telemetry"):
            return Response(json.dumps({"state": "IDLE", "mission_id": None,
                "armed": False, "gps_fix": 1, "gps_sats": 0,
                "battery_pct": None, "lat": 0.0, "lon": 0.0}).encode())
        pytest.fail("diagnostic attempted an unapproved endpoint")
    monkeypatch.setattr(receiver, "urlopen", fake_urlopen)
    status, detail = process_real_test(
        {"node_id": "operator-diagnostic", "lat": 21.1, "lon": 79.0},
        "http://local", "", False, False, 1000, True)
    assert status == "completed"
    assert "Pixhawk connected" in detail and "GPS" in detail
    assert calls == ["http://local/health", "http://local/telemetry"]


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


def test_audio_upload_is_bound_to_signed_alert(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("scripts.wifi_alert_receiver.verify_audio_clip",
                        lambda *args: None)
    server = AlertServer(("127.0.0.1", 0), KEY, NODES,
                         tmp_path / "alerts.sqlite3")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        body, signature = signed_event()
        alert = Request(base + "/alert", body,
                        headers={"X-Alert-Signature": signature}, method="POST")
        with urlopen(alert, timeout=2):
            pass
        pcm = bytes(64_000)
        mac = hmac.new(KEY, b"pole-1:1:" + pcm, hashlib.sha256).hexdigest()
        clip = Request(base + "/audio", pcm,
                       headers={"X-Node-Id": "pole-1", "X-Alert-Seq": "1",
                                "X-Audio-Signature": mac}, method="POST")
        with urlopen(clip, timeout=2) as response:
            assert json.load(response)["accepted"] is True
        assert (tmp_path / "clips" / "pole-1-1.wav").exists()
        with pytest.raises(HTTPError) as duplicate:
            urlopen(clip, timeout=2)
        assert duplicate.value.code == 409
        forged = Request(base + "/audio", pcm,
                         headers={"X-Node-Id": "pole-1", "X-Alert-Seq": "2",
                                  "X-Audio-Signature": mac}, method="POST")
        with pytest.raises(HTTPError) as invalid:
            urlopen(forged, timeout=2)
        assert invalid.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_next_signed_alert_can_claim_only_one_bench_check(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VANNI_BENCH_NEXT_ALERT", "1")
    monkeypatch.setenv("VANNI_PILOT_READY", "1")
    called = threading.Event()
    monkeypatch.setattr("scripts.wifi_alert_receiver._run_one_bench_check",
                        lambda *args: called.set())
    server = AlertServer(("127.0.0.1", 0), KEY, NODES,
                         tmp_path / "alerts.sqlite3")
    try:
        maybe_trigger_one_bench_check(server, {"node_id": "pole-1", "seq": 1,
                                               "sound_score": 0.01})
        assert called.wait(1)
        maybe_trigger_one_bench_check(server, {"node_id": "pole-1", "seq": 2,
                                               "sound_score": 0.99})
        with sqlite3.connect(server.database) as db:
            rows = db.execute("SELECT node_id, seq FROM bench_once").fetchall()
        assert rows == [("pole-1", 1)]
    finally:
        server.server_close()
