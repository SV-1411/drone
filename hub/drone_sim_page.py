"""Compatibility route for the VanniKawachh geographic flight viewer.

/drone-sim is retained as the familiar demo URL but uses the same final
implementation as /drone-flight.
"""
from fastapi.responses import HTMLResponse
from .drone_flight_final import HTML


def attach(app):
    @app.get("/drone-sim", response_class=HTMLResponse)
    def drone_sim_page():
        return HTML
