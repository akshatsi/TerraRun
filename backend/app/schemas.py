import math
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=100)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_name: str
    user_email: EmailStr


MAX_FIXES_PER_RUN = 100_000


class FixIn(BaseModel):
    """One raw GPS fix. `t` is the fix's own GPS time (ISO 8601)."""
    lat: float = Field(allow_inf_nan=False)
    lng: float = Field(allow_inf_nan=False)
    t: datetime
    accuracy_m: Optional[float] = Field(default=None, allow_inf_nan=False)
    speed_mps: Optional[float] = Field(default=None, allow_inf_nan=False)
    heading_deg: Optional[float] = Field(default=None, allow_inf_nan=False)
    altitude_m: Optional[float] = Field(default=None, allow_inf_nan=False)


class RunCreateRequest(BaseModel):
    # New contract: raw fixes with timestamps. The server decides the distance.
    client_run_id: Optional[str] = Field(default=None, min_length=8, max_length=64)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    client_distance_km: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    fixes: Optional[list[FixIn]] = Field(default=None, max_length=MAX_FIXES_PER_RUN)

    duration_seconds: int = Field(ge=0, le=7 * 24 * 3600)

    # Legacy contract: phone-computed numbers and untimed [[lat, lng], ...].
    distance_km: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    avg_speed: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    route_coordinates: Optional[list[list[float]]] = Field(
        default=None, max_length=MAX_FIXES_PER_RUN
    )

    @model_validator(mode="after")
    def _check(self):
        if self.fixes is None and self.distance_km is None:
            raise ValueError("send either fixes or distance_km")
        if self.route_coordinates is not None:
            for pt in self.route_coordinates:
                if len(pt) != 2 or not all(math.isfinite(v) for v in pt):
                    raise ValueError("route_coordinates must be [[lat, lng], ...]")
        return self


class ProcessingInfo(BaseModel):
    algorithm_version: Optional[str] = None
    quality: Optional[str] = None
    accepted_fixes: Optional[int] = None
    rejected_fixes: Optional[int] = None
    gap_count: Optional[int] = None
    uncertain_distance_m: Optional[float] = None
    raw_distance_km: Optional[float] = None
    client_distance_km: Optional[float] = None
    moving_time_s: Optional[float] = None


class TerritoryInfo(BaseModel):
    observed_area_sq_m: float = 0.0
    awarded_area_sq_m: float = 0.0
    total_area_sq_m: float = 0.0
    kind: str = "none"        # loop | route | none
    reason: str = ""


class RunResponse(BaseModel):
    id: int
    user_id: int
    distance_km: float
    duration_seconds: int
    avg_speed: float
    created_at: datetime
    # Processed route (MultiLineString) when present, else the raw route.
    route_geojson: Optional[dict] = None
    territory_geojson: Optional[dict] = None
    processing: Optional[ProcessingInfo] = None
    territory: Optional[TerritoryInfo] = None
    duplicate: bool = False

    class Config:
        from_attributes = True


class ProfileStatsResponse(BaseModel):
    total_distance_km: float
    total_runs: int
    avg_speed: float
    # --- NEW: optional territory area ---
    territory_area_sq_m: float = 0.0


class UserProfileResponse(BaseModel):
    user_name: str
    user_email: EmailStr


# ---------------------------------------------------------------------------
# NEW: Territory-specific response schemas
# ---------------------------------------------------------------------------

class TerritoryResponse(BaseModel):
    user_id: int
    user_name: str
    area_sq_m: float
    geojson: Optional[dict] = None


class TerritoryListResponse(BaseModel):
    territories: list[TerritoryResponse]


# ---------------------------------------------------------------------------
# Social: following, feed (see docs/social.md)
# ---------------------------------------------------------------------------

class UserCard(BaseModel):
    id: int
    name: str
    total_distance_km: float = 0.0
    total_runs: int = 0
    territory_area_sq_m: float = 0.0
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False
    follows_you: bool = False
    bio: Optional[str] = None


class FeedUser(BaseModel):
    id: int
    name: str


class RunSummary(BaseModel):
    run_id: int
    created_at: datetime
    distance_km: float
    duration_seconds: int
    avg_speed: float
    territory_kind: Optional[str] = None
    awarded_area_sq_m: float = 0.0
    route_geojson: Optional[dict] = None


class FeedItem(RunSummary):
    user: FeedUser


class UserDetail(UserCard):
    recent_runs: list[RunSummary] = []


# ---------------------------------------------------------------------------
# Run detail and profile editing (see docs/social.md, v2)
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not 2 <= len(v) <= 40:
            raise ValueError("name must be 2 to 40 characters")
        return v

    @field_validator("bio")
    @classmethod
    def _bio(cls, v):
        if v is None:
            return v
        v = v.strip()
        if len(v) > 160:
            raise ValueError("bio must be at most 160 characters")
        return v or None


class SplitOut(BaseModel):
    km: int
    distance_m: float
    duration_s: float
    pace_s_per_km: int
    elevation_change_m: Optional[float] = None


class RunDetailTerritory(BaseModel):
    kind: str = "none"
    awarded_area_sq_m: float = 0.0
    reason: str = ""


class RunDetail(BaseModel):
    run_id: int
    created_at: datetime
    user: FeedUser
    is_mine: bool
    distance_km: float
    duration_seconds: int
    moving_time_s: Optional[float] = None
    avg_speed_kmh: float = 0.0
    avg_pace_s_per_km: Optional[int] = None
    elevation_gain_m: Optional[float] = None
    max_speed_kmh: Optional[float] = None
    quality: Optional[str] = None
    territory: RunDetailTerritory
    route_geojson: Optional[dict] = None
    awarded_geojson: Optional[dict] = None
    splits: list[SplitOut] = []
