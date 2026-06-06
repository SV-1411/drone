"""Pydantic models for the trigger API."""
from __future__ import annotations

import time
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class TriggerRequest(BaseModel):
    lat: float = Field(..., description="Target latitude in decimal degrees")
    lon: float = Field(..., description="Target longitude in decimal degrees")
    priority: str = Field("normal", description="low | normal | high | critical")
    incident_type: str = Field("generic", description="Free-form incident category")
    altitude_m: Optional[float] = Field(None, description="Override cruise altitude in metres")
    hover_s: Optional[int] = Field(None, description="Override hover duration in seconds")

    @field_validator("lat")
    @classmethod
    def _lat_range(cls, v: float) -> float:
        if not -90.0 <= v <= 90.0:
            raise ValueError("lat must be between -90 and 90")
        return v

    @field_validator("lon")
    @classmethod
    def _lon_range(cls, v: float) -> float:
        if not -180.0 <= v <= 180.0:
            raise ValueError("lon must be between -180 and 180")
        return v

    @field_validator("priority")
    @classmethod
    def _priority_value(cls, v: str) -> str:
        allowed = {"low", "normal", "high", "critical"}
        if v not in allowed:
            raise ValueError(f"priority must be one of {sorted(allowed)}")
        return v


class WaypointRequest(BaseModel):
    lat: float
    lon: float
    alt: Optional[float] = None


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
