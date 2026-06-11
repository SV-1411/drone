"""Pydantic models for the trigger API.

All coordinates and mission parameters are bounds-checked here, at the edge,
so the flight core never sees an impossible value. Altitude is additionally
capped at 120 m — the small-UAS AGL ceiling in most jurisdictions.
"""
from __future__ import annotations

import time
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

MIN_ALTITUDE_M = 2.0
MAX_ALTITUDE_M = 120.0
MAX_HOVER_S = 3600


class TriggerRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Target latitude in decimal degrees")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Target longitude in decimal degrees")
    priority: str = Field("normal", description="low | normal | high | critical")
    incident_type: str = Field("generic", max_length=100, description="Free-form incident category")
    altitude_m: Optional[float] = Field(
        None, ge=MIN_ALTITUDE_M, le=MAX_ALTITUDE_M,
        description=f"Override cruise altitude in metres ({MIN_ALTITUDE_M}-{MAX_ALTITUDE_M})",
    )
    hover_s: Optional[int] = Field(
        None, ge=0, le=MAX_HOVER_S,
        description=f"Override hover duration in seconds (0-{MAX_HOVER_S})",
    )

    @field_validator("priority")
    @classmethod
    def _priority_value(cls, v: str) -> str:
        allowed = {"low", "normal", "high", "critical"}
        if v not in allowed:
            raise ValueError(f"priority must be one of {sorted(allowed)}")
        return v


class WaypointRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    alt: Optional[float] = Field(None, ge=MIN_ALTITUDE_M, le=MAX_ALTITUDE_M)


class TriggerResponse(BaseModel):
    mission_id: str
    status: str
    estimated_arrival_s: float
    target: List[float]


class MissionStatus(BaseModel):
    mission_id: str
    status: str
    target_lat: float
    target_lon: float
    altitude_m: float
    hover_s: int
    incident_type: str
    priority: str
    queued_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    final_state: Optional[str] = None


class IncidentRecord(BaseModel):
    mission_id: str
    incident_type: str
    priority: str
    target_lat: float
    target_lon: float
    triggered_at: float = Field(default_factory=time.time)
    final_state: Optional[str] = None
