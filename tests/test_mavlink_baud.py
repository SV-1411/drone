"""Serial telemetry must use the same rate as Pixhawk TELEM2."""

from flight_core import mavlink_interface
from types import SimpleNamespace


def dummy_vehicle():
    return SimpleNamespace(version="test", mode=SimpleNamespace(name="STABILIZE"))


def test_serial_connection_uses_configured_baud(monkeypatch):
    calls = []
    monkeypatch.setenv("MAVLINK_BAUD", "57600")
    monkeypatch.setattr(mavlink_interface, "connect",
                        lambda address, **kw: calls.append((address, kw)) or dummy_vehicle())
    mavlink_interface.connect_vehicle("/dev/serial0", retries=1)
    assert calls[0][0] == "/dev/serial0"
    assert calls[0][1]["baud"] == 57600
    assert calls[0][1]["wait_ready"] is False


def test_sitl_connection_does_not_set_serial_baud(monkeypatch):
    calls = []
    monkeypatch.setattr(mavlink_interface, "connect",
                        lambda address, **kw: calls.append((address, kw)) or dummy_vehicle())
    mavlink_interface.connect_vehicle("tcp:127.0.0.1:5760", retries=1)
    assert "baud" not in calls[0][1]
    assert calls[0][1]["wait_ready"] is True
