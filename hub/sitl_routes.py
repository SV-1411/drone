"""HTTP endpoints for a real local ArduPilot/Gazebo SITL bridge.

Render stays stateless enough for the normal browser simulator. A local SITL
bridge posts telemetry here; the flight UI can consume /drone_state_live when
real physics is connected.
"""
from __future__ import annotations

from fastapi import Request

from . import sitl_state


def attach(app):
    @app.post("/sitl-report")
    async def sitl_report(request: Request):
        data = dict(await request.json())
        sitl_state.update(**data)
        return {"ok": True, "source": "ARDUPILOT_SITL_GAZEBO", "state": sitl_state.snapshot()}

    @app.get("/sitl-status")
    def sitl_status():
        state = sitl_state.snapshot(max_age_s=5.0)
        return {"connected": state is not None, "source": "ARDUPILOT_SITL_GAZEBO" if state else "NONE", "state": state}

    @app.get("/drone_state_live")
    def drone_state_live():
        state = sitl_state.snapshot(max_age_s=5.0)
        if state is not None:
            return state
        # Keep the deployed browser demo usable without SITL.
        from . import webapp
        return webapp.phone_drone.snapshot() if webapp.phone_drone.fresh() else webapp.fleet.active()
