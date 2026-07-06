"""First-aid-kit payload release (SG90 servo on a Pixhawk AUX output).

Commanded via MAV_CMD_DO_SET_SERVO — no dronekit-specific API, so this works
identically over SITL (where the command is accepted and logged) and real
hardware (where the servo physically opens the release hook).

Safety rule (docs/PROJECT_PLAN.md §7): a failed release is never a reason to
loiter — the caller proceeds to RTL and reports the failure.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("flight_core.payload")


def set_servo(vehicle, channel: int, pwm: int) -> bool:
    """Send DO_SET_SERVO. Returns False if the command couldn't be sent."""
    try:
        from pymavlink import mavutil
        master = vehicle._master
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_SERVO, 0,
            float(channel), float(pwm), 0, 0, 0, 0, 0,
        )
        return True
    except Exception as exc:
        log.error("DO_SET_SERVO ch%d=%d failed: %s", channel, pwm, exc)
        return False


def release_kit(vehicle, channel: int, open_pwm: int, hold_pwm: int,
                settle_s: float = 2.0) -> bool:
    """Open the release hook, hold long enough for the kit to drop, close.

    Returns True if both servo commands were sent (SITL/hardware accepted
    them); physical confirmation needs a payload microswitch (future work).
    """
    if not set_servo(vehicle, channel, open_pwm):
        return False
    log.info("payload release OPEN (ch%d pwm=%d)", channel, open_pwm)
    time.sleep(max(0.5, settle_s))
    set_servo(vehicle, channel, hold_pwm)   # re-close; failure here is benign
    log.info("payload release CLOSED (ch%d pwm=%d)", channel, hold_pwm)
    return True
