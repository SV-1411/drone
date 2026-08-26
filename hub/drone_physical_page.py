"""Compatibility alias for the physical hardware view.

The canonical route is /drone-hardware. /drone-physical is retained only so
older bookmarks do not break; it uses exactly the same HTML implementation.
"""
from .drone_hardware_page import HTML
from fastapi.responses import HTMLResponse


def attach(app):
    @app.get("/drone-physical", response_class=HTMLResponse)
    def drone_physical_page():
        return HTML
