"""FastAPI trigger surface + WebSocket telemetry stream."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import List, Optional

# Allow `python -m uvicorn trigger_api.main:app` from project root, AND
# `python trigger_api/main.py` directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from flight_core.config import CONFIG
from flight_core.mission_executor import MissionExecutor, MissionSpec, Waypoint
from flight_core.mavlink_interface import haversine_distance_m

from .mission_queue import MissionQueue, new_mission_id
from .models import (
    IncidentRecord,
    MissionStatus,
    TriggerRequest,
    TriggerResponse,
    WaypointRequest,
)

log = logging.getLogger("trigger_api")

executor = MissionExecutor(CONFIG)
queue = MissionQueue(executor)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    queue.start()
    # Best-effort eager connect so first /trigger isn't slow. Non-blocking:
    # if SITL isn't up yet we simply retry on first mission.
    async def _try_connect():
        for _ in range(3):
            try:
                executor.ensure_connected()
                return
            except Exception as exc:
                log.warning("eager connect failed: %s", exc)
                await asyncio.sleep(5)
    asyncio.create_task(_try_connect())
    try:
        yield
    finally:
        queue.stop()
        executor.close()


app = FastAPI(title="Drone Safety Trigger API", version="1.0.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _eta_seconds(target_lat: float, target_lon: float) -> float:
    """Rough ETA from current position to target at 8 m/s cruise."""
    snap = executor.snapshot()
    if snap.lat is None or snap.lon is None:
        # use home as proxy
        d = haversine_distance_m(CONFIG.home_lat, CONFIG.home_lon, target_lat, target_lon)
    else:
        d = haversine_distance_m(snap.lat, snap.lon, target_lat, target_lon)
    cruise_ms = 8.0
    return round(d / cruise_ms + 20.0, 1)  # +20s for arm/takeoff


@app.post("/trigger", response_model=TriggerResponse)
def trigger_mission(req: TriggerRequest) -> TriggerResponse:
    mission_id = new_mission_id()
    spec = MissionSpec(
        mission_id=mission_id,
        target_lat=req.lat,
        target_lon=req.lon,
        altitude_m=req.altitude_m if req.altitude_m is not None else CONFIG.cruise_altitude_m,
        hover_s=req.hover_s if req.hover_s is not None else CONFIG.hover_duration_s,
        priority=req.priority,
        incident_type=req.incident_type,
    )
    queue.enqueue(spec)
    eta = _eta_seconds(req.lat, req.lon)
    return TriggerResponse(
        mission_id=mission_id,
        status="queued",
        estimated_arrival_s=eta,
        target=[req.lat, req.lon],
    )


@app.get("/mission/{mission_id}", response_model=MissionStatus)
def mission_status(mission_id: str) -> MissionStatus:
    qm = queue.get(mission_id)
    if qm is None:
        raise HTTPException(status_code=404, detail=f"mission {mission_id} not found")
    return MissionStatus(
        mission_id=qm.spec.mission_id,
        status=qm.status,
        target_lat=qm.spec.target_lat,
        target_lon=qm.spec.target_lon,
        altitude_m=qm.spec.altitude_m,
        hover_s=qm.spec.hover_s,
        incident_type=qm.spec.incident_type,
        priority=qm.spec.priority,
        queued_at=qm.queued_at,
        started_at=qm.started_at,
        finished_at=qm.finished_at,
        final_state=qm.final_state,
    )


@app.get("/missions", response_model=List[MissionStatus])
def list_missions(limit: int = 50) -> List[MissionStatus]:
    return [
        MissionStatus(
            mission_id=qm.spec.mission_id,
            status=qm.status,
            target_lat=qm.spec.target_lat,
            target_lon=qm.spec.target_lon,
            altitude_m=qm.spec.altitude_m,
            hover_s=qm.spec.hover_s,
            incident_type=qm.spec.incident_type,
            priority=qm.spec.priority,
            queued_at=qm.queued_at,
            started_at=qm.started_at,
            finished_at=qm.finished_at,
            final_state=qm.final_state,
        )
        for qm in queue.list_recent(limit=limit)
    ]


@app.get("/telemetry")
def telemetry():
    return executor.snapshot().to_dict()


@app.post("/mission/{mission_id}/waypoint")
def add_waypoint(mission_id: str, req: WaypointRequest):
    qm = queue.get(mission_id)
    if qm is None:
        raise HTTPException(status_code=404, detail="mission not found")
    if qm.status != "running":
        raise HTTPException(status_code=400, detail=f"mission status is {qm.status}, cannot add waypoint")
    executor.add_waypoint(Waypoint(lat=req.lat, lon=req.lon, alt=req.alt or CONFIG.cruise_altitude_m))
    return {"ok": True, "mission_id": mission_id}


@app.get("/health")
def health():
    snap = executor.snapshot()
    return {
        "ok": True,
        "vehicle_connected": executor.vehicle is not None,
        "state": snap.state,
        "queue_depth": len(queue._pending),  # diagnostic only
    }


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await ws.accept()
    interval = max(0.1, CONFIG.telemetry_interval_ms / 1000.0)
    try:
        while True:
            snap = executor.snapshot().to_dict()
            await ws.send_json(snap)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    except Exception:
        log.exception("telemetry ws closed with error")
