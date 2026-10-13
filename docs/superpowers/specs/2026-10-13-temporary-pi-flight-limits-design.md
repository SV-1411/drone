# Temporary Pi Flight Limits Design

## Goal and scope

For the supervised VanniKawachh Pi-commanded test profile, set the receiver's configured maximum target distance to 1,000 m, but make every Pi-issued takeoff and normal navigation request use 1.0 m relative altitude and 0.5 m/s horizontal ground speed. Do not let a request override the 1.0 m command altitude. Disable first-aid-kit delivery in this profile rather than allowing its existing 3.0 m drop-altitude command. Pixhawk-controlled emergency modes, including Return-to-Launch (RTL), remain independent.

This is a **command profile**, not a claim that the aircraft will remain physically below 1.0 m. The Pi has no terrain-clearance sensor guarantee; Pixhawk's own navigation, barometer, and RTL behavior can differ from the command. This design does not authorize a 1 km flight.

## Current behavior and constraints

- `scripts/wifi_alert_receiver.py` uses `VANNI_REAL_MAX_TARGET_M` (1,000 m by default) but clamps the no-battery prototype branch to 30 m. It separately requires the captured home to be within 20 m of the aircraft.
- The live Pi currently has `VANNI_PROTOTYPE_NO_BATTERY=1`. Its flight API reports `GEOFENCE_RADIUS=60`, `MAX_MISSION_DURATION=120`, `CRUISE_ALT=1`, and `CRUISE_SPEED=0.5`. These are separate interlocks. At 0.5 m/s, 1 km of horizontal travel alone takes at least 2,000 seconds; a return would take longer. Do not silently enlarge the 60 m geofence or 120-second timeout in this change.
- `trigger_api/models.py` currently accepts explicit altitude overrides from 2 to 120 m. `trigger_api/main.py` uses the 1 m default only when an override is absent, and accepts optional waypoint altitudes.
- `flight_core/mission_executor.py` passes the mission altitude to `simple_takeoff` and normal `simple_goto`, and passes `config.cruise_speed_ms` as `groundspeed` for normal `simple_goto`. Its kit-delivery path issues a separate command to `payload_drop_alt_m`, currently 3 m. Pixhawk RTL is a mode change, not a Pi-controlled 1 m/0.5 m/s waypoint command.
- The Pi currently reports no Pixhawk heartbeat or fresh GPS/battery telemetry. The previously implemented fresh-home gate must remain intact; no flight command may be sent as part of validation.

## Design

1. Add an explicit `VANNI_TEMP_FLIGHT_PROFILE=1` switch to `flight_core.config.Config` and set it only in the Pi flight API's prototype drop-in. The profile is active only with a physical serial link, so SITL and other deployments keep their existing behavior. When active, its authoritative Pi-command altitude is 1.0 m and its normal horizontal navigation speed is 0.5 m/s. Allow an explicit 1.0 m altitude through request parsing, but the flight API rejects any active-profile trigger or added waypoint that supplies a different altitude; omitted altitudes resolve to 1.0 m. It rejects `deliver_kit=true` for this profile.
2. The mission executor independently rejects an active-profile mission or added waypoint that would command above 1.0 m, including direct in-process calls that bypass HTTP validation. It uses 1.0 m in its Pi-issued takeoff and normal goto requests and explicitly requests 0.5 m/s for normal goto, regardless of a conflicting generic `CRUISE_SPEED` setting; API ETA and `/health` report the effective 0.5 m/s value. The kit-delivery branch is unreachable for this profile. Do not change Pixhawk RTL altitude or speed parameters. The 0.5 m/s value is a requested horizontal speed, not a guaranteed measured speed or a vertical takeoff/RTL speed limit.
3. Change only the receiver's no-battery target-distance clamp from 30 m to 1,000 m, still bounded by `VANNI_REAL_MAX_TARGET_M`. Keep the receiver's home-proximity, GPS, RC/pilot-readiness, battery-if-reported, 60 m flight-API geofence, and 120-second timeout checks. Targets more than 60 m from captured home will continue to be rejected by the flight API; the 1 km figure is an upper target-setting value for later readiness work, not an effective current flight radius.
4. Keep the new battery monitor's installation/calibration and any later change to geofence or mission duration as a separate decision after live battery, GPS, MAVLink heartbeat, RC takeover, and short supervised flights are verified. Do not treat this code change as a flight-readiness sign-off.

## Error handling and validation

- API requests for altitude above 1.0 m or kit delivery return a clear client error without queuing a mission. Direct mission-executor calls fail before arming or issuing a takeoff/goto command.
- API requests with no altitude continue to resolve to 1.0 m; added waypoints follow the same rule. Normal goto commands carry 0.5 m/s. These rules do not constrain emergency RTL.
- Unit tests cover rejected trigger/waypoint altitude overrides, rejected kit delivery, the executor's direct-call guard, normal 1.0 m/0.5 m/s command arguments, the 1,000 m receiver cap, and preservation of the 60 m/120-second prototype checks. Run the full unit tier and staging tests on the Pi without arming. Compare staged code with the live Pi's newer deployed files before installation, back up those files, and verify `/health` and `/telemetry` after restarting only the affected services.
- Physical outdoor flight, a 1 km route, and actual speed/altitude tracking are **not** validation steps for this change. With no current Pixhawk heartbeat, those outcomes cannot be asserted.
