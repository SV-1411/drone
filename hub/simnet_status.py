"""Small status endpoint for the live SIMNET/ArduPilot bridge."""
from fastapi.responses import JSONResponse


def attach(app, bridge):
    @app.get("/simnet-status")
    def simnet_status():
        if bridge is None:
            return JSONResponse({"configured": False, "connected": False, "state": "DISABLED"})
        return bridge.snapshot()
