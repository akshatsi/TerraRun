"""
Leaderboard response schemas.
"""

import uuid

from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: uuid.UUID
    username: str
    avatar_url: str | None = None
    territory_area_m2: float
    total_distance_m: float


class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
    total: int
