"""VanniKawachh hub — Stage-2 verification and drone dispatch service."""

# All browser views are attached to the same FastAPI app used by Render.
from . import webapp as _webapp
from .config import CONFIG as _CONFIG
from .drone_sim_page import attach as _attach_drone_sim
from .drone_flight_v2 import attach as _attach_drone_flight
from .drone_hardware_page import attach as _attach_drone_hardware
from .drone_physical_page import attach as _attach_drone_physical
from .physical_sim import PhysicalDispatcher, PhysicalFleet

# Replace only the visual/phone-test fleet under the existing public API with
# the phased physical simulator. The Wokwi /node-alert endpoint stays intact.
_physical_fleet = PhysicalFleet(_CONFIG.drone_bases, _CONFIG.drone_speed_ms)
_webapp.fleet = _physical_fleet
_webapp.sim_dispatcher = PhysicalDispatcher(_physical_fleet)

_attach_drone_sim(_webapp.app)
_attach_drone_flight(_webapp.app)
_attach_drone_hardware(_webapp.app)
_attach_drone_physical(_webapp.app)
