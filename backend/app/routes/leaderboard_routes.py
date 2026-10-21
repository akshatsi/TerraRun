from datetime import datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.deps import friend_ids_subquery, get_optional_user
from app.models import Run, User, Territory

router = APIRouter()


def week_start(now: datetime | None = None) -> datetime:
    """Monday 00:00 UTC of the current week."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday, time.min, tzinfo=timezone.utc)


@router.get("/leaderboard")
def get_leaderboard(
    scope: Literal["all", "friends"] = Query(default="all"),
    period: Literal["all", "week"] = Query(default="all"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    query = (
        db.query(
            User.id,
            User.name,
            func.sum(Run.distance_km).label("total_distance"),
            func.count(Run.id).label("total_runs"),
            func.avg(Run.avg_speed).label("avg_speed"),
        )
        .join(Run, Run.user_id == User.id)
    )
    if scope == "friends":
        if current_user is None:
            raise HTTPException(status_code=401, detail="Missing token")
        query = query.filter(User.id.in_(friend_ids_subquery(current_user)))
    if period == "week":
        query = query.filter(Run.created_at >= week_start())
    results = (
        query.group_by(User.id, User.name)
        .order_by(func.sum(Run.distance_km).desc())
        .all()
    )

    # Pre-fetch territory areas for all users with territories
    territory_map = {}
    territories = db.query(Territory.user_id, Territory.area_sq_m).all()
    for t in territories:
        territory_map[t.user_id] = round(t.area_sq_m, 2)

    me_id = current_user.id if current_user else None
    leaderboard = []
    for r in results:
        leaderboard.append({
            "name": r.name,
            "total_distance": float(r.total_distance or 0),
            "total_runs": int(r.total_runs or 0),
            "avg_speed": float(r.avg_speed or 0),
            "territory_area": territory_map.get(r.id, 0.0),
            "user_id": r.id,
            "is_me": r.id == me_id,
        })

    return leaderboard
