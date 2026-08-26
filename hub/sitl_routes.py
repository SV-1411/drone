"""HTTP endpoints for a real local ArduPilot/Gazebo SITL bridge.

A local SITL bridge posts telemetry here. When fresh telemetry exists, the
existing /drone_state endpoint is transparently served from SITL so all of the
existing dashboard/hardware pages consume the real flight state without adding
a second mission API.
"""
from __future__ import annotations

from fastapi import Request

from . import sitl_state


def _fallback_state():
    from . import webapp
    return webapp.phone_drone.snapshot() if webapp.phone_drone.fresh() else webapp.fleet.active()


def _live_state():
    state = sitl_state.snapshot(max_age_s=5.0)
    return state if state is not None else _fallback_state()


def attach(app):
    @app.post("/sitl-report")
    async def sitl_report(request: Request):
        data = dict(await request.json())
        state = sitl_state.update(**data)
        return {"ok": True, "source": "ARDUPILOT_SITL_GAZEBO", "state": state}

    @app.get("/sitl-status")
    def sitl_status():
        state = sitl_state.snapshot(max_age_s=5.0)
        return {
            "connected": state is not None,
            "source": "ARDUPILOT_SITL_GAZEBO" if state else "BROWSER_SIM",
            "state": state,
        }

    @app.get("/drone_state_live")
    def drone_state_live():
        return _live_state()

    # The original /drone_state route is attached by webapp.py before this
    # module. Replace only its endpoint so no existing page needs to know which
    # simulator is currently authoritative.
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == "/drone_state" and hasattr(route, "endpoint"):
            route.endpoint = _live_state
            break
