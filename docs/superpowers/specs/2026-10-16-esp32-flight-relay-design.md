# ESP32-S3 cloud flight relay

Approved in chat on 2026-10-16. This replaces the lost Pi's command consumer;
it does not replace server audio verification or dashboard operator approval.

## Contract

- Phone audio is verified by Render. The operator approves a fresh voice incident.
- ESP polls HTTPS `/edge/real-test/claim/next` using the existing dashboard
  operator key, provisioned once locally. Per the user's follow-up, no separate
  Pi/device token is required. Legacy Pi authentication remains compatible.
- Only approved `phone-` commands can enter the flight path. The public
  diagnostic command is answered without arm, mission upload, or flight.
- Server command expiry remains 60 seconds. Add `created` and `expires_at` to
  the claim response without removing fields used by the existing Pi consumer.
- ESP validates absolute expiry using synchronized time and refuses stale,
  malformed, duplicate, nonfinite or out-of-range coordinates.
- Firmware initially boots flight-locked. Local commissioning, after live
  preflight and manual-flight/battery/link-failsafe validation, saves real mode
  so each subsequent dashboard-approved mission is autonomous across reboots.
  A separate temporary local authorization permits one mission for 120 seconds.
  Cloud credentials alone cannot commission the aircraft.
- Persist the consumed command ID before any flight command. Persist an active
  command flag and require explicit local recovery after restart. Never resume
  or re-arm automatically after a reset during a mission. Only one mission runs at once.

## Hardware and provisioning

The attached ESP32-S3 has 8 MB flash and 8 MB embedded PSRAM. USB CDC is COM12;
Pixhawk USB is COM13. Use a separate hardware UART on the S3's labelled
RX/GPIO44 and TX/GPIO43 pins at 57600 8N1, with common ground to TELEM2.
Keep debug/provisioning on native USB; never print debug text into the MAVLink
UART. Disable hardware flow control on Pixhawk TELEM2.

Before replacing firmware, retain a full flash backup in ignored `.cache/`.
Wi-Fi SSID/password and operator key are provisioned over USB into an isolated
NVS namespace. Do not print, commit, or embed credentials in firmware sources.
The operator chose the laptop's current Wi-Fi network. ESP32-S3 needs 2.4 GHz.
Validate HTTPS using a CA bundle and synchronized clock; never `setInsecure()`.

## Flight behavior

Use ArduPilot GUIDED with confirmed mode, command acknowledgements and heartbeat
confirmation. Command takeoff to 1.0 m relative to launch home; request 0.5 m/s
horizontal ground speed; fly to approved coordinates, return to fresh launch
coordinates at the same commanded altitude, then LAND. This is a sequenced
MAVLink mission executed by the ESP, not a persisted AUTO mission. The local
supervisor observes each phase and does not advance on an unconfirmed command.

The initial local target radius is 20 m, mission duration 120 seconds, navigation
arrival radius 1.5 m, no hover or payload release. These are prototype defaults
pending aircraft endurance and manual-flight validation. Reject larger targets.
Read the relevant Pixhawk speed settings and reject activation if its configured
horizontal/climb/descent limits exceed the requested 0.5 m/s; do not silently
rewrite aircraft parameters. Set and acknowledge DO_CHANGE_SPEED before travel.

Altitude is a requested target, not an exact physical ceiling or terrain height.
Normal return uses a GUIDED home waypoint to avoid an ordinary RTL altitude
climb. Independent Pixhawk failsafes retain authority and can select a different
altitude or speed. Do not disable battery, RC, EKF, fence, or arming checks.

Preflight requires fresh heartbeat/position/GPS/RC/system status and fresh launch
home, disarmed vehicle, 3D GPS with at least eight satellites, plausible battery
voltage, known battery cell count and per-cell minimum, no critical system
state, onboard pre-arm health, and explicit local pilot readiness. Today's
recorded battery failsafe remains a blocker until physical measurements agree
with calibrated Pixhawk readings and manual flight is validated.

In flight, telemetry and heartbeat acquisition must remain independent of HTTPS
calls. Apply bounded network timeouts. Low battery/GPS/EKF or mission timeout
requests confirmed LAND, never disarms in the air. RC pilot takeover ends ESP
navigation commands; ESP must not fight the pilot or overwrite Pixhawk's own
failsafe mode. Lost MAVLink prevents further commands; configured Pixhawk
onboard link-loss handling must be verified before activation. Loss of Wi-Fi
does not interrupt the local landing/navigation supervisor.

## Verification and handoff

Compile firmware for the actual S3 board. Exercise policy/state transitions
against simulated telemetry and MAVLink with no connection to real COM ports.
Verify expiry, replay rejection, failed mode/arm acknowledgements, reset during
mission, manual takeover, GPS/battery loss, and mission timeout. Test cloud
claim expiry and compatibility. Flash the bench image with the local flight
authorization absent. Only read-only telemetry/configuration requests and
heartbeats may be sent during the physical connection check. Report firmware,
simulation, cloud authentication, UART and flight readiness separately.
