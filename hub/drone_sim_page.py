"""Compatibility route for the VanniKawachh GCS geographic flight simulator."""
from fastapi.responses import HTMLResponse
from .drone_flight_gcs import HTML


def attach(app):
    @app.get("/drone-sim", response_class=HTMLResponse)
    def drone_sim_page():
        return HTML
