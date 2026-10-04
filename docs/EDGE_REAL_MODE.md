# ESP alerts, Render modes, and the drone Pi

The Render dashboard has two separate modes:

- **Demo mode** displays signed sensing-node alerts and sends the nearest *simulated* drone to the latest node position. It never contacts Pixhawk.
- **Real mode** creates an authenticated, 60-second operator test request. The drone Pi claims it at most once and rejects it unless its local flight API and safety gates are ready. The button bypasses *audio verification only*, not flight readiness.

The current ESP32-S3/KY-037 path sends signed `sound_level_candidate` alerts to the Pi. Those alerts are monitored and mirrored to Render, but **never automatically dispatch a physical drone**. This is deliberate: the present microphone/model combination has produced high-confidence false alarms in quiet conditions. The ESP packet also contains no audio clip for independent verification. Do not describe this as proven Bachao recognition.

## Configuration, once physical flight has been validated

The Pi receiver reads `%h/.config/vannikawachh/wifi-alert.env` through its user systemd service. The following optional settings control the real-test path; they default to locked:

```text
VANNI_RELAY_URL=https://vannikawachh-hub.onrender.com
VANNI_RELAY_PI_TOKEN=<private Pi polling token>
VANNI_REAL_MODE=1
VANNI_PILOT_READY=1
VANNI_FLIGHT_API_URL=http://127.0.0.1:8000
VANNI_FLIGHT_API_TOKEN=<private local flight API token, at least 32 characters>
VANNI_REAL_MAX_TARGET_M=1000
```

`VANNI_PILOT_READY` means a qualified operator is physically present with a working RC takeover path. It is not an unattended deployment switch. The local `trigger_api` must itself be configured for the physical UART link, with `API_TOKEN` matching `VANNI_FLIGHT_API_TOKEN`, `ALLOW_REAL_DISPATCH=1`, and a surveyed local `HOME_LAT`/`HOME_LON`. Do not disable ArduPilot pre-arm, battery, GPS, or geofence checks to make a test pass.

The Pi rejects the request if flight mode is locked, the local API is unavailable, the aircraft is armed/busy, GPS lacks a 3D fix or eight satellites, battery telemetry is absent/below 30%, or its current GPS position is farther from the node than `VANNI_REAL_MAX_TARGET_M`. The flight API also applies its own geofence and mission-state checks. The operator key is stored privately as `VANNI_OPERATOR_KEY` on Render and entered into the dashboard only when requesting a physical test.

The Pixhawk TELEM2 connection tested here runs at 57,600 baud. The Pi has a boot-enabled `vanni-flight-api.service` with `MAVLINK_CONNECTION=/dev/serial0` and `MAVLINK_BAUD=57600`. It listens only on `127.0.0.1:8000`, requires an API token, and has `ALLOW_REAL_DISPATCH=0` in its private environment file. `/health` confirms a MAVLink connection and IDLE state; that does **not** establish flight readiness. Current telemetry reports no usable GPS position or battery data. The service's default home coordinates are not the physical launch site and must be surveyed and configured before any real-dispatch enablement.

Do not enable real mode while testing at home with the node configured to the college coordinates. The node location is surveyed and fixed; changing it requires explicitly reprovisioning the ESP and Pi registry. The current props-off arm test is not a navigation test.

## Network path

If ESP and Pi share a LAN, ESP posts directly to the Pi. The Pi mirrors the already-signed packet to Render when it has internet, so the physical node is visible on the cloud dashboard. The present flashed ESP firmware is direct-LAN only; the cloud-capable sketch in `firmware/ky037_wifi_node` cannot run on that board until it is uploaded over USB. Until then, an ESP on a different network cannot reach the Pi by itself. Render's free local SQLite storage is ephemeral, so cloud events and queued commands can disappear on a restart; it is not a durable emergency transport.

## Readiness still required

Before enabling physical dispatch: fix or replace the KY-037 microphone path and measure false positives; verify a manual outdoor flight, RC takeover, battery monitor, GPS/compass, geofence, vehicle weight/balance, and a full SITL rehearsal of the exact mission. Only after independent audio verification exists should live mic alerts be considered for automatic dispatch. The dashboard's real-test button is a supervised operator test, not that future automatic pipeline.
