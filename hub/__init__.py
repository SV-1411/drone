"""VanniKawachh hub — Stage-2 verification and drone dispatch service.

Runs on the locality Raspberry Pi 5. Receives Stage-1 alerts from sensing
nodes (LoRa via the gateway ESP32, or simulated), verifies the audio with
PANNs (or an energy-heuristic fallback on dev machines), fuses PIR/LDR/time
evidence into a severity score, and dispatches the response drone through
the existing trigger API.
"""

# The deployed web app is the source of truth for the public demo. Attach the
# browser-based 3D drone hardware view to that same FastAPI app so there is no
# second localhost server or second pipeline to keep in sync.
try:
    from . import webapp as _webapp
    from .drone_sim_page import attach as _attach_drone_sim
    _attach_drone_sim(_webapp.app)
except Exception:
    # Keep package imports usable for CLI/tests that do not load the web app.
    pass
