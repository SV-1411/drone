"""Compatibility route for the VanniKawachh geographic flight viewer."""
from fastapi.responses import HTMLResponse
from .drone_flight_clean import HTML


def attach(app):
    @app.get("/drone-sim", response_class=HTMLResponse)
    def drone_sim_page():
        return HTML
