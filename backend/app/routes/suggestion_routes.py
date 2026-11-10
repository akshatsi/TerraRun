"""GET /suggestions: loops that grow the runner's territory. See docs/route-suggestions.md."""
import json
from datetime import datetime, timedelta, timezone
from statistics import median

import shapely
from fastapi import APIRouter, Depends, HTTPException, Query
from shapely import wkb
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Follow, Run, Territory, User
from app.routing import OwnedArea, PlannerConfig, PlannerInput, plan_routes
from app.routing.roads import (
    RoadDataUnavailable, circle_bbox, get_roads, overpass_fetch,
)
from app.schemas import RouteSuggestion, StolenFrom, SuggestionsResponse

router = APIRouter(tags=["suggestions"])

DEFAULT_PACE_S_PER_KM = 390  # 6:30 /km
DEFAULT_DISTANCE_M = 2000.0
USUAL_MIN_M, USUAL_MAX_M = 800.0, 8000.0
TARGET_MIN_M, TARGET_MAX_M = 300.0, 15_000.0
MAX_SEARCH_RADIUS_M = 3000.0
RECENT_RUNS = 10
POPULARITY_DAYS = 90
POPULARITY_NEAR_M = 10.0
TERRITORY_MARGIN_M = 500.0


def get_road_fetcher():
    """Overridden in tests so they never reach the network."""
    return overpass_fetch


def runner_stats(db: Session, user_id: int) -> tuple[int, float]:
    """(pace in s/km, usual distance in m) from the last 10 runs with distance.

    Pace uses moving time when the run has it, so stops don't slow it down.
    """
    rows = db.execute(
        select(Run.distance_km, func.coalesce(Run.moving_time_s, Run.duration_seconds))
        .where(Run.user_id == user_id, Run.distance_km > 0)
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(RECENT_RUNS)
    ).all()
    if not rows:
        return DEFAULT_PACE_S_PER_KM, DEFAULT_DISTANCE_M
    total_km = sum(r[0] for r in rows)
    total_s = sum(r[1] for r in rows)
    pace = round(total_s / total_km) if total_s > 0 else DEFAULT_PACE_S_PER_KM
    usual = median(r[0] for r in rows) * 1000.0
    return max(pace, 1), min(max(usual, USUAL_MIN_M), USUAL_MAX_M)


def _territories(db: Session, user_ids: list[int], bbox) -> list[OwnedArea]:
    if not user_ids:
        return []
    s, w, n, e = bbox
    rows = db.execute(
        select(Territory.user_id, text("ST_AsBinary(territories.geom)"))
        .where(
            Territory.user_id.in_(user_ids),
            Territory.geom.op("&&")(text("ST_MakeEnvelope(:w, :s, :e, :n, 4326)").bindparams(
                w=w, s=s, e=e, n=n)),
        )
    ).all()
    out = []
    for uid, raw in rows:
        geom = wkb.loads(bytes(raw))
        if not geom.is_empty and geom.geom_type in ("Polygon", "MultiPolygon"):
            out.append(OwnedArea(user_id=uid, geometry=geom))
    return out


def _popularity(db: Session, friend_ids: list[int], osm_ids: list[int], bbox) -> dict[int, int]:
    """osm_id -> how many friends' recent runs passed within ~10 m of the road."""
    if not friend_ids or not osm_ids:
        return {}
    s, w, n, e = bbox
    since = datetime.now(timezone.utc) - timedelta(days=POPULARITY_DAYS)
    stmt = text(
        """
        WITH runs_near AS (
            SELECT id, processed_route_geom AS g FROM runs
            WHERE user_id = ANY(:friends) AND created_at >= :since
              AND processed_route_geom IS NOT NULL
              AND processed_route_geom && ST_MakeEnvelope(:w, :s, :e, :n, 4326)
        )
        SELECT w.osm_id, COUNT(DISTINCT r.id)
        FROM road_ways w
        JOIN runs_near r ON ST_DWithin(w.geom::geography, r.g::geography, :near)
        WHERE w.osm_id = ANY(:ids)
        GROUP BY w.osm_id
        """
    ).bindparams(bindparam("friends"), bindparam("ids"))
    rows = db.execute(stmt, {
        "friends": friend_ids, "since": since, "ids": osm_ids, "near": POPULARITY_NEAR_M,
        "w": w, "s": s, "e": e, "n": n,
    }).all()
    return {int(r[0]): int(r[1]) for r in rows}


@router.get("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(
    lat: float = Query(ge=-90, le=90, allow_inf_nan=False),
    lng: float = Query(ge=-180, le=180, allow_inf_nan=False),
    distance_km: float | None = Query(default=None, ge=0.3, le=15, allow_inf_nan=False),
    minutes: float | None = Query(default=None, ge=3, le=180, allow_inf_nan=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    fetcher=Depends(get_road_fetcher),
):
    if distance_km is not None and minutes is not None:
        raise HTTPException(status_code=422, detail="Send distance_km or minutes, not both")

    pace, usual_m = runner_stats(db, current_user.id)
    if distance_km is not None:
        target_m = distance_km * 1000.0
    elif minutes is not None:
        target_m = minutes * 60.0 / pace * 1000.0
    else:
        target_m = usual_m
    target_m = min(max(target_m, TARGET_MIN_M), TARGET_MAX_M)

    radius_m = min(target_m / 2.0, MAX_SEARCH_RADIUS_M)
    try:
        roads = get_roads(db, (lat, lng), radius_m, fetcher=fetcher)
    except RoadDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    def respond(suggestions=(), message=None):
        return SuggestionsResponse(
            target_distance_km=round(target_m / 1000.0, 2),
            pace_s_per_km=pace,
            suggestions=list(suggestions),
            message=message,
        )

    if not roads:
        return respond(message="No main roads found near you.")

    friend_ids = list(db.execute(
        select(Follow.followee_id).where(Follow.follower_id == current_user.id)
    ).scalars())
    names = {}
    if friend_ids:
        names = dict(db.execute(select(User.id, User.name).where(User.id.in_(friend_ids))).all())

    bbox = circle_bbox((lat, lng), radius_m + TERRITORY_MARGIN_M)
    mine = _territories(db, [current_user.id], bbox)
    friends = _territories(db, friend_ids, bbox)
    popularity = _popularity(db, friend_ids, [r.osm_id for r in roads], bbox)

    found = plan_routes(
        PlannerInput(
            start=(lat, lng),
            roads=roads,
            my_user_id=current_user.id,
            my_territory=mine[0] if mine else None,
            friend_territories=friends,
            target_distance_m=target_m,
            popularity=popularity,
        ),
        PlannerConfig(),
    )
    if not found:
        return respond(message="No road loops near you yet.")

    out = []
    for s in found:
        km = s.distance_m / 1000.0
        stolen_from = [
            StolenFrom(user_id=uid, name=names.get(uid, "Runner"), area_sq_m=round(area, 1))
            for uid, area in sorted(s.stolen_by_user.items(), key=lambda kv: -kv[1])
            if area > 0
        ]
        out.append(RouteSuggestion(
            label=s.label,
            reason=s.reason,
            distance_km=round(km, 2),
            estimated_minutes=max(1, round(km * pace / 60.0)),
            new_area_sq_m=round(s.new_area_sq_m, 1),
            stolen_area_sq_m=round(s.stolen_area_sq_m, 1),
            stolen_from=stolen_from,
            gain_sq_m=round(s.gain_sq_m, 1),
            route_geojson={
                "type": "LineString",
                "coordinates": [[p[1], p[0]] for p in s.route],
            },
            area_geojson=json.loads(shapely.to_geojson(s.enclosed)),
        ))
    return respond(out)
