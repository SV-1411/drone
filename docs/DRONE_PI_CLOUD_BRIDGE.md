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

1. The sensing Pi sends an audio clip to Render `/phone-alert` with its private
   `VANNI_SENSING_TOKEN` bearer token.
2. Only an actual server-confirmed, dispatched audio incident enters the
   one-time `/edge/drone/claim/next` queue. Public button reports cannot do so.
3. The drone Pi checks fresh Pixhawk telemetry and local physical-flight
   limits before claiming a command. It checks the incident coordinates again
   before handing the target to localhost `/trigger`.
4. The local flight service controls the Pixhawk state machine and reports its
   own mission outcome. A `mission_queued` cloud result means only that the
   local API accepted the request; it does not mean the drone flew or landed.

The queue route is still named `/edge/drone` and its private token is still
named `VANNI_DRONE_ESP_TOKEN` for compatibility with the earlier ESP firmware.
The consumer can now be this Pi instead. The Render database is SQLite on an
ephemeral free-tier filesystem, so it is for a prototype, not a reliable
emergency service.

## Current blockers

The live Render site returns 404 for `/edge/drone/status`; it is running an
older `main` build. Deploy the updated `main` before setting up the private
drone and sensing tokens. The Pi can reach Render `/edge/status` over HTTPS,
and the cloud listener is running, but it cannot claim the absent queue.

Indoor telemetry currently has GPS fix 1, zero satellites, position (0,0),
and a battery voltage near 0.03 V despite reporting 99%. That voltage is not
a usable LiPo measurement. Do not enable claim mode or physical dispatch until
the GPS, power-module reading, RC takeover, geofence, launch home, and manual
outdoor flight have been checked. The service will not treat a percentage
alone as valid battery telemetry.

## Private configuration after hardware validation

Render needs `VANNI_SENSING_TOKEN` and `VANNI_DRONE_ESP_TOKEN` as separate
private environment variables, each at least 32 random characters. The
sensing Pi uses the sensing token. The drone Pi reads its token and settings
from `%h/.config/vannikawachh/drone-pi-cloud.env` through the cloud service.
Keep this file mode 0600; never commit it. Its eventual contents are:

```text
VANNI_RELAY_URL=https://vannikawachh-hub.onrender.com
VANNI_DRONE_ESP_TOKEN=<same private drone token as Render>
VANNI_FLIGHT_API_URL=http://127.0.0.1:8000
VANNI_FLIGHT_API_TOKEN=<local flight API token>
VANNI_CLOUD_CLAIM_ENABLED=0
VANNI_PILOT_READY=0
```

The flight API token must match its localhost service configuration. Keep
`VANNI_CLOUD_CLAIM_ENABLED=0` and `ALLOW_REAL_DISPATCH=0` until the readiness
checks and a supervised flight are validated. The bridge caps a supervised
target to 30 m from the current Pixhawk position, and requires a captured
launch home, a plausible battery voltage and charge level, 3D GPS with at
least eight satellites, and conservative speed/altitude/geofence limits.

Check the two services with `systemctl --user status
vanni-drone-pi-flight-locked.service` and `systemctl --user status
vanni-drone-pi-cloud.service`. The read-only API endpoints are
`http://127.0.0.1:8000/health` and `/telemetry` on the Pi.
