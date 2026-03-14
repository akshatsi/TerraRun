"""
Leaderboard routes — global and local rankings.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.leaderboard import LeaderboardResponse
from app.services.leaderboard_service import get_global_leaderboard, get_local_leaderboard

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/global", response_model=LeaderboardResponse)
async def global_leaderboard(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Top users globally by territory area."""
    entries, total = await get_global_leaderboard(db, limit=limit, offset=offset)
    return LeaderboardResponse(entries=entries, total=total)


@router.get("/local", response_model=LeaderboardResponse)
async def local_leaderboard(
    city: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Top users in a specific city by territory area."""
    entries, total = await get_local_leaderboard(db, city=city, limit=limit, offset=offset)
    return LeaderboardResponse(entries=entries, total=total)
