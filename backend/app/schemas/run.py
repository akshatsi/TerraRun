"""
Run request / response schemas.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GpsPointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    altitude: float | None = None
    timestamp: datetime


class CreateRunRequest(BaseModel):
    """Submit a completed run with its GPS track."""
    started_at: datetime
    ended_at: datetime
    gps_points: list[GpsPointIn] = Field(min_length=2)


class RunResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    distance_m: float
    duration_s: int
    avg_pace: float | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class RunListResponse(BaseModel):
    runs: list[RunResponse]
    total: int
