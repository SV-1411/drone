# ESP alerts, Render modes, and the drone Pi

## Phone sensing prototype

The public `/node` page can use a phone's browser location and microphone.
`SIMULATE DISTRESS` records a test-button report and moves only a simulated
drone. Live voice windows and stressed emergency words still pass through the
server's existing acoustic verification. If that pipeline confirms an incident,
Render records a `voice` mobile incident with the reported position and GPS
accuracy. The phone user does not need the operator key to report distress.

The dashboard shows recent phone reports. A fresh verified voice report with a
browser-reported GPS accuracy of 50 m or better can be selected by an operator
for a physical mission. The operator key authorizes that request. The drone Pi
then claims the command through its existing private polling channel and runs
its local flight readiness checks before posting the phone coordinates to
`/trigger`. Button reports cannot be promoted to a physical mission. The
phone's GPS and audio can be spoofed or replayed, so public reporting must not
directly authorize an aircraft launch.

The Pi still requires `VANNI_REAL_MODE=1`, `VANNI_PILOT_READY=1`, a connected
Pixhawk, valid GPS telemetry, a nearby target, and
`ALLOW_REAL_DISPATCH=1` on its local flight API. Keep these switches disabled
until the aircraft has completed manual outdoor flight tests. Render's free
SQLite database is ephemeral; use durable storage before relying on phone
reports in a real emergency.

Battery telemetry is required by default. A separate, local-only
`VANNI_PROTOTYPE_NO_BATTERY=1` setting permits a supervised short prototype
flight with no battery reading. It does not override a reported battery below
30%, missing GPS, an armed vehicle, or an incorrect home location. In this
mode the target must be within 30 m of the aircraft, the configured home
within 20 m, and the request fixes altitude at 3 m with no observation hover
or payload drop. The flight API must advertise a mission timeout of at most
120 s and a geofence radius of at most 60 m, or the Pi refuses dispatch.
There is **no automatic low-battery response** without a battery sensor.
Use this only after manual outdoor flight and RC takeover have been proven,
with a person physically supervising the entire test. The public operator
key and Pi flight locks remain in place.

The Render dashboard has two separate modes:

- **Demo mode** displays signed sensing-node alerts and sends the nearest *simulated* drone to the latest node position. It never contacts Pixhawk.
- **Real mode** creates an authenticated, 60-second operator test request. The drone Pi claims it at most once and rejects it unless its local flight API and safety gates are ready. The button bypasses *audio verification only*, not flight readiness.

The current ESP32-S3/KY-037 path sends signed `sound_level_candidate` alerts to the Pi. Those alerts are monitored and mirrored to Render, but **never automatically dispatch a physical drone**. This is deliberate: the present microphone/model combination has produced high-confidence false alarms in quiet conditions. The new sketch also sends the captured two-second PCM clip over the local Wi-Fi link to the Pi. The Pi stores it as a WAV, attempts YAMNet verification if that backend is installed, and reports the result to Render. This path still needs hardware upload and validation. Do not describe it as proven Bachao recognition.

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
# Optional supervised prototype only, after the limits below are configured:
VANNI_PROTOTYPE_NO_BATTERY=1
```

`VANNI_PILOT_READY` means a qualified operator is physically present with a working RC takeover path. It is not an unattended deployment switch. The local `trigger_api` must itself be configured for the physical UART link, with `API_TOKEN` matching `VANNI_FLIGHT_API_TOKEN`, `ALLOW_REAL_DISPATCH=1`, and a surveyed local `HOME_LAT`/`HOME_LON`. For the unmonitored-battery prototype, set `MAX_MISSION_DURATION=120` and `GEOFENCE_RADIUS=60` on the flight API before enabling the optional Pi flag. Do not disable ArduPilot pre-arm or GPS checks to make a test pass.

The Pi rejects the request if flight mode is locked, the local API is unavailable, the aircraft is armed/busy, GPS lacks a 3D fix or eight satellites, known battery capacity is below 30%, or its current GPS position is farther from the node than the applicable test radius. Missing battery telemetry is rejected unless the local prototype flag and stricter limits above are set. The flight API also applies its own geofence and mission-state checks. The operator key is stored privately as `VANNI_OPERATOR_KEY` on Render and entered into the dashboard only when requesting a physical test.

The Pixhawk TELEM2 connection tested here runs at 57,600 baud. The Pi has a boot-enabled `vanni-flight-api.service` with `MAVLINK_CONNECTION=/dev/serial0` and `MAVLINK_BAUD=57600`. It listens only on `127.0.0.1:8000`, requires an API token, and has `ALLOW_REAL_DISPATCH=0` in its private environment file. `/health` confirms a MAVLink connection and IDLE state; that does **not** establish flight readiness. Current telemetry reports no usable GPS position or battery data. The service's default home coordinates are not the physical launch site and must be surveyed and configured before any real-dispatch enablement.

## Props-off dashboard bench check

For a supervised wiring check only, the dashboard's `Simulate distress (real
test)` button creates an operator request without depending on a fresh ESP
alert. The Pi can route that request to `POST /bench/props-off-arm-check`.
This route issues one
ordinary Pixhawk arm request, observes for two seconds, and sends an ordinary
disarm request. It has no takeoff, mode, throttle, motor-test, waypoint, or
mission command. It requires the private API key plus both local temporary
switches `BENCH_PROPS_REMOVED=1` and `VANNI_BENCH_WEB_TEST=1`. The switches
must be removed immediately after the observed test. Pixhawk pre-arm checks
remain enabled and can reject the request; no pre-arm check is bypassed.
The separate `Request flight to node` button continues to require a recent
signed node alert and all navigation checks.

For a single automatic props-off demonstration, `VANNI_BENCH_NEXT_ALERT=1`
on the Pi receiver consumes the next authenticated ESP alert regardless of
its sound confidence and requests the same normal arm/disarm check. The
receiver stores the consumed request in SQLite before contacting Pixhawk, so
subsequent false alerts and service restarts cannot repeat it. It also needs
`VANNI_PILOT_READY=1`, the local flight API token, and the flight API's
`BENCH_PROPS_REMOVED=1`. This setting is for the one supervised test, not
the permanent distress policy.

Do not enable real mode while testing at home with the node configured to the college coordinates. The node location is surveyed and fixed; changing it requires explicitly reprovisioning the ESP and Pi registry. The current props-off arm test is not a navigation test.

## Network path

If ESP and Pi share a LAN, ESP posts directly to the Pi. The Pi mirrors the already-signed packet to Render when it has internet, so the physical node is visible on the cloud dashboard. The present flashed ESP firmware is direct-LAN only; the cloud-capable sketch in `firmware/ky037_wifi_node` cannot run on that board until it is uploaded over USB. Until then, an ESP on a different network cannot reach the Pi by itself. Render's free local SQLite storage is ephemeral, so cloud events and queued commands can disappear on a restart; it is not a durable emergency transport.

## Readiness still required

Before enabling physical dispatch: fix or replace the KY-037 microphone path and measure false positives; verify a manual outdoor flight, RC takeover, battery monitor, GPS/compass, geofence, vehicle weight/balance, and a full SITL rehearsal of the exact mission. Only after independent audio verification exists should live mic alerts be considered for automatic dispatch. The dashboard's real-test button is a supervised operator test, not that future automatic pipeline.
