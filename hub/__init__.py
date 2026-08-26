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

# When SIMNET_HOST and SIMNET_PORT are supplied, the same public /node-alert
# dispatch path switches to an actual ArduPilot/SIMNET MAVLink session.
if os.environ.get("SIMNET_HOST", "").strip() and os.environ.get("SIMNET_PORT", "").strip():
    try:
        from simulation.simnet_fleet import SimnetFleet
        _fleet = SimnetFleet(_CONFIG.drone_bases, _CONFIG.drone_speed_ms)
        _dispatcher = _fleet
    except Exception:
        # Never take production down because an optional simulator dependency is
        # unavailable. The visual mission backend remains available.
        pass

_webapp.fleet = _fleet
_webapp.sim_dispatcher = _dispatcher
_attach_drone_sim(_webapp.app)
_attach_drone_flight(_webapp.app)
_attach_drone_hardware(_webapp.app)
_attach_drone_physical(_webapp.app)
