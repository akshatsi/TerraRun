import json
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Follow, Run, Territory, User
from app.schemas import (
    FeedItem, FeedUser, ProfileUpdate, RunSummary, UserCard, UserDetail, UserProfileResponse,
)

router = APIRouter(tags=["social"])


def _utc(dt):
    return dt.astimezone(timezone.utc) if dt is not None and dt.tzinfo else dt


def user_cards(db: Session, me: User, user_ids: list[int]) -> dict[int, UserCard]:
    """UserCards for the given ids, in one query (counts aggregated in SQL)."""
    if not user_ids:
        return {}
    runs_n = (select(func.count(Run.id)).where(Run.user_id == User.id)
              .correlate(User).scalar_subquery())
    runs_km = (select(func.coalesce(func.sum(Run.distance_km), 0.0))
               .where(Run.user_id == User.id).correlate(User).scalar_subquery())
    area = (select(func.coalesce(func.max(Territory.area_sq_m), 0.0))
            .where(Territory.user_id == User.id).correlate(User).scalar_subquery())
    followers = (select(func.count()).select_from(Follow)
                 .where(Follow.followee_id == User.id).correlate(User).scalar_subquery())
    following = (select(func.count()).select_from(Follow)
                 .where(Follow.follower_id == User.id).correlate(User).scalar_subquery())
    i_follow = exists().where(and_(Follow.follower_id == me.id, Follow.followee_id == User.id))
    follows_me = exists().where(and_(Follow.follower_id == User.id, Follow.followee_id == me.id))
    rows = db.execute(
        select(User.id, User.name, User.bio, runs_km, runs_n, area, followers, following,
               i_follow, follows_me).where(User.id.in_(user_ids))
    ).all()
    return {
        r[0]: UserCard(
            id=r[0], name=r[1], bio=r[2], total_distance_km=float(r[3] or 0),
            total_runs=int(r[4] or 0), territory_area_sq_m=round(float(r[5] or 0), 2),
            followers_count=int(r[6]), following_count=int(r[7]),
            is_following=bool(r[8]), follows_you=bool(r[9]),
        )
        for r in rows
    }


def _cards_in_order(db: Session, me: User, ids: list[int]) -> list[UserCard]:
    cards = user_cards(db, me, ids)
    return [cards[i] for i in ids if i in cards]


def _run_summaries(db: Session, where, limit: int, with_user: bool):
    """Newest-first runs matching `where` (a SQLAlchemy clause)."""
    route = func.ST_AsGeoJSON(func.coalesce(Run.processed_route_geom, Run.route_geom))
    q = (
        select(Run.id, Run.created_at, Run.distance_km, Run.duration_seconds,
               Run.avg_speed, Run.territory_kind, Run.awarded_area_sq_m,
               route, Run.user_id, User.name)
        .join(User, User.id == Run.user_id)
        .where(where)
        .order_by(Run.id.desc())
        .limit(limit)
    )
    out = []
    for r in db.execute(q).all():
        data = dict(
            run_id=r[0], created_at=_utc(r[1]), distance_km=r[2],
            duration_seconds=r[3], avg_speed=r[4], territory_kind=r[5],
            awarded_area_sq_m=round(r[6] or 0.0, 2),
            route_geojson=json.loads(r[7]) if r[7] else None,
        )
        out.append(
            FeedItem(**data, user=FeedUser(id=r[8], name=r[9])) if with_user
            else RunSummary(**data)
        )
    return out


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/me", response_model=UserProfileResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserProfileResponse(user_name=current_user.name, user_email=current_user.email)


@router.patch("/users/me", response_model=UserCard)
def update_me(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sent = payload.model_fields_set
    if "name" in sent:
        if payload.name is None:
            raise HTTPException(status_code=422, detail="name cannot be null")
        current_user.name = payload.name
    if "bio" in sent:
        current_user.bio = payload.bio
    db.commit()
    return user_cards(db, current_user, [current_user.id])[current_user.id]


@router.get("/users/me/card", response_model=UserCard)
def my_card(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return user_cards(db, current_user, [current_user.id])[current_user.id]


@router.get("/users/search", response_model=list[UserCard])
def search_users(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    term = q.strip()
    if len(term) < 2:
        raise HTTPException(status_code=422, detail="q must be at least 2 characters")
    esc = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    ids = [
        r[0] for r in db.execute(
            select(User.id)
            .where(User.id != current_user.id)
            .where(User.name.ilike(f"%{esc}%", escape="\\")
                   | User.email.ilike(f"{esc}%", escape="\\"))
            .order_by(User.name.ilike(f"{esc}%", escape="\\").desc(), User.name, User.id)
            .limit(limit)
        ).all()
    ]
    return _cards_in_order(db, current_user, ids)


@router.get("/users/{user_id}", response_model=UserDetail)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_user_or_404(db, user_id)
    card = user_cards(db, current_user, [user_id])[user_id]
    recent = _run_summaries(db, Run.user_id == user_id, 5, with_user=False)
    return UserDetail(**card.model_dump(), recent_runs=recent)


@router.post("/users/{user_id}/follow", response_model=UserCard)
def follow(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")
    _get_user_or_404(db, user_id)
    db.execute(
        pg_insert(Follow)
        .values(follower_id=current_user.id, followee_id=user_id)
        .on_conflict_do_nothing()
    )
    db.commit()
    return user_cards(db, current_user, [user_id])[user_id]


@router.delete("/users/{user_id}/follow", response_model=UserCard)
def unfollow(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot unfollow yourself")
    _get_user_or_404(db, user_id)
    db.query(Follow).filter(
        Follow.follower_id == current_user.id, Follow.followee_id == user_id
    ).delete()
    db.commit()
    return user_cards(db, current_user, [user_id])[user_id]


@router.get("/me/following", response_model=list[UserCard])
def my_following(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ids = [r[0] for r in db.execute(
        select(Follow.followee_id).where(Follow.follower_id == current_user.id)
        .order_by(Follow.created_at.desc(), Follow.followee_id.desc())
    ).all()]
    return _cards_in_order(db, current_user, ids)


@router.get("/me/followers", response_model=list[UserCard])
def my_followers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ids = [r[0] for r in db.execute(
        select(Follow.follower_id).where(Follow.followee_id == current_user.id)
        .order_by(Follow.created_at.desc(), Follow.follower_id.desc())
    ).all()]
    return _cards_in_order(db, current_user, ids)


@router.get("/feed", response_model=list[FeedItem])
def feed(
    limit: int = Query(default=20, ge=1, le=50),
    before_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    where = Run.user_id.in_(
        select(Follow.followee_id).where(Follow.follower_id == current_user.id)
    )
    if before_id is not None:
        where = and_(where, Run.id < before_id)
    return _run_summaries(db, where, limit, with_user=True)
