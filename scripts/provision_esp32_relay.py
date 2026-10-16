"""Provision a bench-connected ESP32-S3 without displaying credentials.

Opening USB serial can reset an ESP32. Use only while Pixhawk is disarmed and
propellers are removed. This helper never sends flight authorization.
"""
from __future__ import annotations

import argparse
import getpass
import json
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import serial


def current_wifi() -> tuple[str, str]:
    """Export only the currently connected profile; erase temporary XML on exit."""
    proc = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    profiles = re.findall(r"^\s*Profile\s*:\s*(.+?)\s*$", proc.stdout, re.M)
    if proc.returncode or len(profiles) != 1:
        raise RuntimeError("Cannot identify one current Windows Wi-Fi profile; use manual provisioning")
    with tempfile.TemporaryDirectory(prefix="vanni-wifi-") as folder:
        exported = subprocess.run(["netsh", "wlan", "export", "profile",
                                   "name=" + profiles[0], "key=clear", "folder=" + folder],
                                  capture_output=True)
        files = list(Path(folder).glob("*.xml"))
        if exported.returncode or len(files) != 1:
            raise RuntimeError("Windows did not export the current Wi-Fi profile")
        root = ET.parse(files[0]).getroot()
        ns = {"w": "http://www.microsoft.com/networking/WLAN/profile/v1"}
        ssid = root.findtext("w:SSIDConfig/w:SSID/w:name", namespaces=ns)
        password = root.findtext("w:MSM/w:security/w:sharedKey/w:keyMaterial", namespaces=ns)
        if not ssid or password is None:
            raise RuntimeError("Current network has no usable personal Wi-Fi password; use a WPA2 hotspot")
        return ssid, password


def exchange(port: str, payload: dict, timeout: float = 12) -> list[dict]:
    device = serial.Serial()
    device.port, device.baudrate, device.timeout = port, 115200, .2
    device.dtr = device.rts = False
    replies: list[dict] = []
    with device:
        time.sleep(2)
        device.reset_input_buffer()
        device.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = device.readline()
            try:
                reply = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(reply, dict):
                continue
            # Explicit allowlist: never echo an arbitrary firmware response containing secrets.
            safe = {k: v for k, v in reply.items() if k in (
                "firmware", "chip", "flight_locked", "state", "wifi_configured",
                "wifi_connected", "operator_key_configured", "cells", "heartbeat_fresh",
                "mavlink_rx_packets", "mavlink_tx_packets", "armed", "gps_fix",
                "uart_rx_bytes", "clock_synced", "relay_http", "commissioned",
                "satellites", "battery_v", "battery_pct", "preflight", "detail",
                "configured", "restarting", "error", "relay_auth_ok", "http",
                "nav_speed_ms", "climb_speed_ms", "descent_speed_ms", "link_failsafe_ready")}
            if safe:
                print(json.dumps(safe))
                replies.append(safe)
            if payload["op"] == "configure" and ("configured" in reply or "error" in reply):
                break
            if payload["op"] == "authcheck" and ("relay_auth_ok" in reply or "error" in reply):
                break
            if payload["op"] == "status" and "firmware" in reply:
                break
    return replies


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM12")
    parser.add_argument("--current-wifi", action="store_true")
    parser.add_argument("--wifi-only", action="store_true", help="Do not prompt for the operator key")
    parser.add_argument("--cells", type=int, choices=range(2, 7))
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--authcheck", action="store_true")
    args = parser.parse_args()
    if args.status or args.authcheck:
        exchange(args.port, {"op": "authcheck" if args.authcheck else "status"})
        return
    if args.current_wifi:
        ssid, password = current_wifi()
    else:
        ssid = input("2.4GHz Wi-Fi SSID: ").strip()
        password = getpass.getpass("Wi-Fi password (hidden): ")
    payload = {"op": "configure", "ssid": ssid, "password": password}
    if not args.wifi_only:
        token = getpass.getpass("Dashboard operator key (hidden): ").strip()
        if len(token) < 32 or "\r" in token or "\n" in token:
            raise SystemExit("Operator key must be at least 32 characters and contain no newlines")
        payload["operator_key"] = token
    if args.cells:
        payload["cells"] = args.cells
    replies = exchange(args.port, payload)
    if not any(r.get("configured") is True for r in replies):
        raise SystemExit("Device did not confirm provisioning")


if __name__ == "__main__":
    main()
