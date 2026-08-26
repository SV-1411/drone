"""VanniKawachh hub — Stage-2 verification and drone dispatch service."""
import os

from . import webapp as _webapp
from .config import CONFIG as _CONFIG
from .drone_sim_page import attach as _attach_drone_sim
from .drone_flight_clean import attach as _attach_drone_flight
from .drone_hardware_clean import attach as _attach_drone_hardware
from .drone_physical_page import attach as _attach_drone_physical
from .physical_sim_clean import PhysicalDispatcher, PhysicalFleet

# Default deployment-safe visual backend.
_fleet = PhysicalFleet(_CONFIG.drone_bases, _CONFIG.drone_speed_ms)
_dispatcher = PhysicalDispatcher(_fleet)

# When SIMNET_HOST and SIMNET_PORT are supplied, switch the existing public
# /node-alert dispatch path to the real ArduPilot/SIMNET MAVLink session.
if os.environ.get("SIMNET_HOST", "").strip() and os.environ.get("SIMNET_PORT", "").strip():
    try:
        from .simnet_bridge import SimnetMavlinkBridge
        from .simnet_fleet import SimnetFleetAdapter, SimnetDispatcher
        _bridge = SimnetMavlinkBridge()
        _bridge.connect()
        _fleet = SimnetFleetAdapter(_fleet, _bridge)
        _dispatcher = SimnetDispatcher(_fleet)
    except Exception:
        # Keep production startup safe if the optional simulator connection is
        # temporarily unavailable. The fallback visual backend remains usable.
        _bridge = None

_webapp.fleet = _fleet
_webapp.sim_dispatcher = _dispatcher
_attach_drone_sim(_webapp.app)
_attach_drone_flight(_webapp.app)
_attach_drone_hardware(_webapp.app)
_attach_drone_physical(_webapp.app)
