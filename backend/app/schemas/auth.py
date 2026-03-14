"""
Auth request / response schemas.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── Requests ──

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    city: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Responses ──

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    avatar_url: str | None = None
    city: str | None = None
    total_distance_m: float = 0.0
    territory_area_m2: float = 0.0
    streak_days: int = 0
    last_run_date: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True
