# Prepared 1 km Flight Profile Design

## Intent

Keep the receiver's 1,000 m target cap and prepare a separate physical-aircraft 1,000 m API geofence, without treating this as approval or evidence for a 1 km flight. The Pi currently has no Pixhawk heartbeat or battery telemetry. At 0.5 m/s a 1 km outbound-and-return route takes at least 4,000 s before takeoff, hover, or contingency time; no defensible mission timeout can be selected without measured usable battery endurance and a tested cruise speed.

## Modes and interlocks

- Preserve the existing supervised no-battery prototype profile at a 60 m API geofence and 120 s timeout. Its receiver health check continues to reject larger settings.
- Add an explicit prepared long-range profile with a 1,000 m API geofence. It is disabled for dispatch by default, even if an existing environment file sets `ALLOW_REAL_DISPATCH=1`. The API and executor must reject long-range missions without a separate explicit readiness switch; a restart must not silently unlock them.
- Do not remove the short-range no-battery limit or treat missing battery readings as healthy. Long-range activation requires live battery voltage/current monitoring and a measured endurance budget; until then the profile remains non-flying. The Pi's fresh grounded Pixhawk GPS home, heartbeat, RC/pilot checks, and Pixhawk pre-arm checks remain mandatory.
- The API geofence is distinct from Pixhawk's own fence. Do not change Pixhawk parameters from the old parameter export; read the live parameters after telemetry is connected. RTL altitude and speed remain Pixhawk-controlled.
- Keep Pi-issued normal takeoff/navigation at 1.0 m and 0.5 m/s in the prepared profile for now. Neither is a physical guarantee; 1.0 m over unknown terrain is not approved for a 1 km route.

## Readiness and verification

Unit tests must prove the 1,000 m profile is reported yet cannot queue or execute a mission while locked, including direct executor calls. The no-battery 60 m/120 s tests must still pass. Deployment must preserve the Pi's fresh-home code, use backups, and verify read-only `/health` and `/telemetry`; no `/trigger`, arming, motor, or flight call is a verification step. Flight readiness requires a later review of live MAVLink/GPS/RC/Pixhawk-fence/battery data and a speed/duration choice based on measured endurance. Logs from a first 1 km flight are not a substitute for those checks.
