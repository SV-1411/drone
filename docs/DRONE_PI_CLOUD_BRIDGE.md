# Drone Pi cloud bridge, 25 October 2026

The drone now carries the Raspberry Pi 4B at `192.168.137.195` instead of the
drone ESP32. Pixhawk TELEM2 TX goes to Pi physical pin 10, TELEM2 RX to pin 8,
and GND to pin 9; TELEM2 5 V is disconnected. The Pi UART is `/dev/serial0`
at 57,600 baud. A read-only test received Pixhawk heartbeats and
`SERIAL2_BAUD=57`, proving bidirectional MAVLink communication. No flight or
motor command was used for this link test.

The Pi has two user services. `vanni-drone-pi-flight-locked.service` owns the
serial port and exposes the flight API only on localhost. It currently has
`ALLOW_REAL_DISPATCH=0`, home coordinates of zero, and no API token, so real
missions are refused. `vanni-drone-pi-cloud.service` monitors the local API
and Render; its claim mode is off by default. Both services were enabled at
boot on this Pi. The cloud bridge never opens the serial port directly.

The intended verified path is:

1. The sensing Pi signs each audio request with its local Ed25519 private key.
   Render verifies it using the public key committed in `device_signatures.py`.
2. Only an actual server-confirmed, dispatched audio incident enters the
   one-time `/edge/drone/claim/next` queue. Public button reports cannot do so.
3. The drone Pi checks fresh Pixhawk telemetry and local physical-flight
   limits before claiming a command. It checks the incident coordinates again
   before handing the target to localhost `/trigger`.
4. The local flight service controls the Pixhawk state machine and reports its
   own mission outcome. A `mission_queued` cloud result means only that the
   local API accepted the request; it does not mean the drone flew or landed.

The queue route is still named `/edge/drone` for compatibility with the earlier
ESP firmware. The consumer can now be this Pi instead. The Render database is SQLite on an
ephemeral free-tier filesystem, so it is for a prototype, not a reliable
emergency service.

## Current blockers

Render now exposes `/edge/drone/status`. Deploy the signed-request update and
verify that this route shows a fresh Pi heartbeat. The old token-only Pi
listener receives HTTP 401 until this update is deployed on both sides.

Indoor telemetry currently has GPS fix 1, zero satellites, position (0,0),
and a battery voltage near 0.03 V despite reporting 99%. The user confirmed
that the LiPo is not plugged in during this setup, so the voltage reading is
expected and does not by itself indicate a faulty monitor. Do not enable claim
mode or physical dispatch until the powered voltage, GPS, RC takeover,
geofence, launch home, and manual outdoor flight have been checked. The
service will not treat a percentage alone as valid battery telemetry.

## Device signing and private configuration

Render needs no new environment variables for the signed Pi requests. Only
the two public Ed25519 verification keys are committed. The drone private key
is stored at `/home/vannidrone/.config/vannikawachh/drone-pi-signing.pem`, and
the sensing private key belongs at `~/.config/vannikawachh/sensing-pi-signing.pem`
on the separate sensing Pi. Both files must be mode 0600 and must never be
committed or pasted into chat. A missing sensing key keeps the listener in
simulation-only mode. Signed requests include body hash, URL path and query,
timestamp, and a one-use nonce; Render rejects tampering, old requests, and
replays.

The drone Pi reads non-secret settings from
`%h/.config/vannikawachh/drone-pi-cloud.env` through the cloud service.
Its eventual contents are:

```text
VANNI_RELAY_URL=https://vannikawachh-hub.onrender.com
VANNI_FLIGHT_API_URL=http://127.0.0.1:8000
VANNI_FLIGHT_API_TOKEN=<local flight API token>
VANNI_CLOUD_CLAIM_ENABLED=0
VANNI_PILOT_READY=0
```

The flight API token is local to the Pi and must match its localhost service
configuration; it is not a Render token. Keep
`VANNI_CLOUD_CLAIM_ENABLED=0` and `ALLOW_REAL_DISPATCH=0` until the readiness
checks and a supervised flight are validated. The bridge caps a supervised
target to 30 m from the current Pixhawk position, and requires a captured
launch home, a plausible battery voltage and charge level, 3D GPS with at
least eight satellites, and conservative speed/altitude/geofence limits.

Check the two services with `systemctl --user status
vanni-drone-pi-flight-locked.service` and `systemctl --user status
vanni-drone-pi-cloud.service`. The read-only API endpoints are
`http://127.0.0.1:8000/health` and `/telemetry` on the Pi.
