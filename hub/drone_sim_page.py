"""Compatibility route for the deployed VanniKawachh drone simulator.

The old /drone-sim URL now serves the same geographic 3D flight viewer as
/drone-flight so the demo never shows two different simulator implementations.
"""
from fastapi.responses import HTMLResponse
from .drone_flight_page import HTML


def attach(app):
    @app.get("/drone-sim", response_class=HTMLResponse)
    def drone_sim_page():
        return HTML
