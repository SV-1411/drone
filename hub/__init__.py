"""VanniKawachh hub — Stage-2 verification and drone dispatch service."""
from . import webapp as _webapp
from .config import CONFIG as _CONFIG
from .drone_sim_page import attach as _attach_drone_sim
from .drone_travel_3d import attach as _attach_drone_travel
from .gazebo_flight_view import attach as _attach_gazebo_flight
from .drone_hardware_v4 import attach as _attach_drone_hardware
from .drone_physical_page import attach as _attach_drone_physical
from .sitl_routes import attach as _attach_sitl_routes
from .physical_sim_clean import PhysicalDispatcher, PhysicalFleet

_fleet = PhysicalFleet(_CONFIG.drone_bases, _CONFIG.drone_speed_ms)
_dispatcher = PhysicalDispatcher(_fleet)
_webapp.fleet = _fleet
_webapp.sim_dispatcher = _dispatcher
_attach_drone_sim(_webapp.app)
_attach_drone_travel(_webapp.app)
_attach_drone_hardware(_webapp.app)
_attach_drone_physical(_webapp.app)
_attach_sitl_routes(_webapp.app)
# Keep Gazebo's flight endpoints registered last and independent from the
# browser travel viewer, which has its own /drone-travel-3d route.
_attach_gazebo_flight(_webapp.app)
