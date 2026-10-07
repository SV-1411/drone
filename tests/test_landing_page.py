from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hub import webapp


def test_home_page_shows_only_existing_page_links():
    html = webapp.landing_page()

    for link in (
        'href="/dashboard"',
        'href="/node"',
        'href="/drone-phone"',
        'id="flight-viewer-link"',
    ):
        assert link in html
    assert 'id="vannikawachh-brutalist-ui"' in html
    assert "html body{background:#f4f4f0!important;color:#111!important}" in html
    assert "Project pages" in html
    assert "/edge/status" not in html
    assert "/nodes" not in html
    assert "Flight API" not in html


def test_existing_dashboard_remains_available_at_dashboard_route():
    routes = {
        route.path
        for route in webapp.app.routes
        if getattr(route, "name", None) == "dashboard"
    }

    assert "/dashboard" in routes
    assert "Police Dashboard" in webapp.dashboard()
