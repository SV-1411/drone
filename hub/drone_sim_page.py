"""Compatibility route for the VanniKawachh GCS geographic flight simulator."""
from fastapi.responses import HTMLResponse
from .drone_flight_gcs import HTML
from .ui import brutalist_html


def attach(app):
    @app.get("/drone-sim", response_class=HTMLResponse)
    def drone_sim_page():
        return brutalist_html(HTML)
