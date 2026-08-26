"""Compatibility redirect for the canonical physical hardware view."""
from fastapi.responses import RedirectResponse


def attach(app):
    @app.get("/drone-physical")
    def drone_physical_page():
        return RedirectResponse(url="/drone-hardware", status_code=307)
