"""VanniKawachh hub — Stage-2 verification and drone dispatch service."""
from . import webapp as _webapp
from .config import CONFIG as _CONFIG
from .drone_sim_page import attach as _attach_drone_sim
from .drone_flight_gcs import attach as _attach_drone_flight
from .drone_hardware_clean import attach as _attach_drone_hardware
from .drone_physical_page import attach as _attach_drone_physical
from .physical_sim_clean import PhysicalDispatcher, PhysicalFleet

# Browser/demo backend: deterministic physical mission simulator driven by
# the same Wokwi -> hub -> /drone_state pipeline. No external SIMNET session
# is required for the deployed web demo.
_fleet = PhysicalFleet(_CONFIG.drone_bases, _CONFIG.drone_speed_ms)
_dispatcher = PhysicalDispatcher(_fleet)

_webapp.fleet = _fleet
_webapp.sim_dispatcher = _dispatcher
_attach_drone_sim(_webapp.app)
_attach_drone_flight(_webapp.app)
_attach_drone_hardware(_webapp.app)
_attach_drone_physical(_webapp.app)
