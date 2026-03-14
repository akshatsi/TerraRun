"""
Run routes — create and retrieve runs.
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.run import Run
from app.models.user import User
from app.schemas.run import CreateRunRequest, RunListResponse, RunResponse
from app.services.badge_service import check_badges_after_run
from app.services.run_service import create_run
from app.services.territory_service import update_territory_after_run
from app.utils.dependencies import get_current_user

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def submit_run(
    body: CreateRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit a completed run with GPS points.
    Pipeline: save run → update territory → update user stats → check badges.
    """
    gps_data = [
        {
            "lat": p.lat,
            "lng": p.lng,
            "altitude": p.altitude,
            "timestamp": p.timestamp,
        }
        for p in body.gps_points
    ]

    # 1. Save the run
    run = await create_run(
        db,
        user_id=current_user.id,
        started_at=body.started_at,
        ended_at=body.ended_at,
        gps_points_data=gps_data,
    )

    # 2. Update territory (buffer + union + overlap resolution)
    coords = [(p.lng, p.lat) for p in body.gps_points]
    await update_territory_after_run(db, current_user.id, coords)

    # 3. Update user aggregate stats
    current_user.total_distance_m += run.distance_m

    # Update streak
    today = date.today()
    if current_user.last_run_date:
        last_date = current_user.last_run_date.date() if isinstance(current_user.last_run_date, datetime) else current_user.last_run_date
        delta = (today - last_date).days
        if delta == 1:
            current_user.streak_days += 1
        elif delta > 1:
            current_user.streak_days = 1
        # delta == 0 means already ran today — no change
    else:
        current_user.streak_days = 1

    current_user.last_run_date = datetime.utcnow()

    # 4. Check and award badges
    await check_badges_after_run(db, current_user)

    await db.flush()
    await db.refresh(run)
    return run


@router.get("", response_model=RunListResponse)
async def list_runs(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's runs, newest first."""
    query = (
        select(Run)
        .where(Run.user_id == current_user.id)
        .order_by(Run.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    runs = result.scalars().all()

    count_q = select(func.count()).select_from(Run).where(Run.user_id == current_user.id)
    total = (await db.execute(count_q)).scalar()

    return RunListResponse(runs=runs, total=total)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific run by ID (must belong to the current user)."""
    result = await db.execute(
        select(Run).where(Run.id == run_id, Run.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
