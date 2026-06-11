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

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from flight_core.config import CONFIG
from flight_core.mission_executor import MissionExecutor, MissionSpec, Waypoint
from flight_core.mavlink_interface import haversine_distance_m

from .mission_queue import MissionQueue, QueueFull, new_mission_id
from .models import (
    MissionStatus,
    TriggerRequest,
    TriggerResponse,
    WaypointRequest,
)
from .store import open_store

log = logging.getLogger("trigger_api")

executor = MissionExecutor(CONFIG)
store = open_store(CONFIG.resolved_db_path)
queue = MissionQueue(
    executor,
    max_depth=CONFIG.max_queue_depth,
    history_limit=CONFIG.history_limit,
    store=store,
)


def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Write-endpoint guard. With API_TOKEN unset (SITL/dev) this is a no-op;
    set API_TOKEN in any deployment reachable beyond localhost."""
    if not CONFIG.api_token:
        return
    if x_api_key != CONFIG.api_token:
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    queue.start()
    # Best-effort eager connect so first /trigger isn't slow. Runs in a worker
    # thread — connect_vehicle blocks for up to retries*timeout and must never
    # stall the event loop.
    async def _try_connect():
        for _ in range(3):
            try:
                await asyncio.to_thread(executor.ensure_connected)
                return
            except Exception as exc:
                log.warning("eager connect failed: %s", exc)
                await asyncio.sleep(5)
    asyncio.create_task(_try_connect())
    try:
        yield
    finally:
        queue.stop()
        # If a mission is mid-flight, command RTL before dropping the link.
        await asyncio.to_thread(executor.shutdown_safe)
        if store is not None:
            store.close()


app = FastAPI(title="Drone Safety Trigger API", version="1.1.0", lifespan=_lifespan)

_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _eta_seconds(target_lat: float, target_lon: float) -> float:
    """Rough ETA from current position to target at cruise speed."""
    snap = executor.snapshot()
    if snap.lat is None or snap.lon is None:
        # use home as proxy
        d = haversine_distance_m(CONFIG.home_lat, CONFIG.home_lon, target_lat, target_lon)
    else:
        d = haversine_distance_m(snap.lat, snap.lon, target_lat, target_lon)
    return round(d / CONFIG.cruise_speed_ms + 20.0, 1)  # +20s for arm/takeoff


def _ensure_inside_geofence(lat: float, lon: float, what: str) -> None:
    """Reject targets the geofence failsafe would abort anyway — fail at the
    API edge instead of mid-air."""
    d = haversine_distance_m(CONFIG.home_lat, CONFIG.home_lon, lat, lon)
    if d > CONFIG.geofence_radius_m:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{what} is {d/1000:.1f} km from home — outside the "
                f"{CONFIG.geofence_radius_m/1000:.1f} km geofence"
            ),
        )


@app.post("/trigger", response_model=TriggerResponse, dependencies=[Depends(require_api_key)])
def trigger_mission(req: TriggerRequest) -> TriggerResponse:
    _ensure_inside_geofence(req.lat, req.lon, "target")
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
    try:
        queue.enqueue(spec)
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    eta = _eta_seconds(req.lat, req.lon)
    return TriggerResponse(
        mission_id=mission_id,
        status="queued",
        estimated_arrival_s=eta,
        target=[req.lat, req.lon],
    )


def _to_status(qm) -> MissionStatus:
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


@app.get("/mission/{mission_id}", response_model=MissionStatus)
def mission_status(mission_id: str) -> MissionStatus:
    qm = queue.get(mission_id)
    if qm is None:
        raise HTTPException(status_code=404, detail=f"mission {mission_id} not found")
    return _to_status(qm)


@app.post("/mission/{mission_id}/cancel", dependencies=[Depends(require_api_key)])
def cancel_mission(mission_id: str):
    """Recall the drone. A queued mission is removed; a running mission
    aborts to RTL (the executor blocks the queue until it lands)."""
    result = queue.cancel(mission_id)
    if result is None:
        qm = queue.get(mission_id)
        if qm is None:
            raise HTTPException(status_code=404, detail="mission not found")
        raise HTTPException(status_code=400, detail=f"mission already {qm.status}, cannot cancel")
    return {"ok": True, "mission_id": mission_id, "result": result}


@app.get("/missions", response_model=List[MissionStatus])
def list_missions(limit: int = 50) -> List[MissionStatus]:
    return [_to_status(qm) for qm in queue.list_recent(limit=limit)]


@app.get("/missions/archive")
def list_archived_missions(limit: int = 200):
    """Mission history persisted across restarts (SQLite)."""
    if store is None:
        return []
    return store.load_recent(limit=limit)


@app.get("/telemetry")
def telemetry():
    return executor.snapshot().to_dict()


@app.post("/mission/{mission_id}/waypoint", dependencies=[Depends(require_api_key)])
def add_waypoint(mission_id: str, req: WaypointRequest):
    qm = queue.get(mission_id)
    if qm is None:
        raise HTTPException(status_code=404, detail="mission not found")
    if qm.status != "running":
        raise HTTPException(status_code=400, detail=f"mission status is {qm.status}, cannot add waypoint")
    _ensure_inside_geofence(req.lat, req.lon, "waypoint")
    executor.add_waypoint(Waypoint(lat=req.lat, lon=req.lon, alt=req.alt if req.alt is not None else CONFIG.cruise_altitude_m))
    return {"ok": True, "mission_id": mission_id}


@app.get("/health")
def health():
    snap = executor.snapshot()
    return {
        "ok": True,
        "vehicle_connected": executor.vehicle is not None,
        "state": snap.state,
        "queue_depth": queue.depth(),
        "auth_enabled": bool(CONFIG.api_token),
        "persistence": store is not None,
    }


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await ws.accept()
    interval = max(0.1, CONFIG.telemetry_interval_ms / 1000.0)
    # The full breadcrumb path (up to 500 points) only changes by one point
    # per tick — resend it every 4th frame instead of every frame to keep the
    # stream light over real telemetry links. The client keeps its last copy.
    frame = 0
    try:
        while True:
            snap = executor.snapshot().to_dict()
            if frame % 4 != 0:
                snap.pop("path", None)
            frame += 1
            await ws.send_json(snap)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    except Exception:
        log.exception("telemetry ws closed with error")
