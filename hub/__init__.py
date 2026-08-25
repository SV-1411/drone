"""VanniKawachh hub — Stage-2 verification and drone dispatch service.

Runs on the locality Raspberry Pi 5. Receives Stage-1 alerts from sensing
nodes (LoRa via the gateway ESP32, or simulated), verifies the audio with
PANNs (or an energy-heuristic fallback on dev machines), fuses PIR/LDR/time
evidence into a severity score, and dispatches the response drone through the
existing trigger API.
"""

# Browser demos are attached to the same FastAPI app used by Render.
from . import webapp as _webapp
from .drone_sim_page import attach as _attach_drone_sim
from .drone_flight_page import attach as _attach_drone_flight

_attach_drone_sim(_webapp.app)
_attach_drone_flight(_webapp.app)
