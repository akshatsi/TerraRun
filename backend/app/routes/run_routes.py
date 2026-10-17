import json
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.gps import ALGORITHM_VERSION, RawFix, TrackConfig, process_track
from app.models import GpsFix, Run, User
from app.schemas import ProcessingInfo, RunCreateRequest, RunResponse, TerritoryInfo
from app.auth import decode_access_token
from app.territory import MIN_AWARD_DISTANCE_M, claim_territory, user_territory_summary

router = APIRouter(prefix="/runs", tags=["runs"])


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# Legacy payloads carry no timestamps. We invent them so the engine's
# time-based checks stay neutral: consecutive points are spaced as if the
# runner moved at LEGACY_ASSUMED_SPEED_MPS, but never less than 1 s and never
# more than LEGACY_MAX_DT_S apart. Point pairs further than about
# LEGACY_MAX_DT_S * max_speed_mps (120 m) still read as implausible jumps and
# are rejected, and no pair is split as a gap (the cap is under long_gap_s).
LEGACY_ASSUMED_SPEED_MPS = 3.0
LEGACY_MAX_DT_S = 10.0


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(min(1.0, math.sqrt(a)))


def _legacy_fixes(coords: list[list[float]]) -> list[RawFix]:
    fixes: list[RawFix] = []
    t = 0.0
    for lat, lng in coords:
        if fixes:
            d = _haversine_m(fixes[-1].lat, fixes[-1].lng, lat, lng)
            t += min(max(d / LEGACY_ASSUMED_SPEED_MPS, 1.0), LEGACY_MAX_DT_S)
        fixes.append(RawFix(lat=lat, lng=lng, t=t))
    return fixes


def _raw_route_ewkt(points: list[tuple[float, float]]) -> str | None:
    """points are (lat, lng). Drops out-of-range pairs; needs two to make a line."""
    pts = [(lng, lat) for lat, lng in points if -90 <= lat <= 90 and -180 <= lng <= 180]
    if len(pts) < 2:
        return None
    return "SRID=4326;LINESTRING(" + ", ".join(f"{x!r} {y!r}" for x, y in pts) + ")"


def _geojson(db: Session, run_id: int, sql_expr: str) -> dict | None:
    raw = db.execute(
        text(f"SELECT ST_AsGeoJSON({sql_expr}) FROM runs WHERE id = :i"), {"i": run_id}
    ).scalar()
    return json.loads(raw) if raw else None


def _kind_reason(run: Run) -> str:
    """Why a saved run got its territory kind (the reason is not stored)."""
    kind = run.territory_kind or "none"
    if kind == "loop":
        return "closed loop: awarded the enclosed area"
    if kind == "route":
        return "route: awarded a strip along the road travelled"
    if run.quality == "poor":
        return "GPS quality too poor to award territory"
    if (run.distance_km or 0.0) * 1000.0 < MIN_AWARD_DISTANCE_M:
        return f"under {MIN_AWARD_DISTANCE_M} m accepted distance"
    if not run.accepted_fix_count:
        return "no route to award"
    return "no territory awarded"


def _run_response(
    db: Session,
    run: Run,
    duplicate: bool = False,
    include_territory_geojson: bool = True,
    reason: str | None = None,
) -> RunResponse:
    route_geojson = _geojson(db, run.id, "COALESCE(processed_route_geom, route_geom)")
    total, terr_geojson = user_territory_summary(
        db, run.user_id, with_geojson=include_territory_geojson
    )
    processing = ProcessingInfo(
        algorithm_version=run.algorithm_version,
        quality=run.quality,
        accepted_fixes=run.accepted_fix_count,
        rejected_fixes=run.rejected_fix_count,
        gap_count=run.gap_count,
        uncertain_distance_m=run.uncertain_distance_m,
        raw_distance_km=run.raw_distance_km,
        client_distance_km=run.client_distance_km,
        moving_time_s=run.moving_time_s,
    )
    territory = TerritoryInfo(
        observed_area_sq_m=round(run.observed_area_sq_m or 0.0, 2),
        awarded_area_sq_m=round(run.awarded_area_sq_m or 0.0, 2),
        total_area_sq_m=round(total, 2),
        kind=run.territory_kind or "none",
        reason=reason or _kind_reason(run),
    )
    return RunResponse(
        id=run.id,
        user_id=run.user_id,
        distance_km=run.distance_km,
        duration_seconds=run.duration_seconds,
        avg_speed=run.avg_speed,
        created_at=run.created_at,
        route_geojson=route_geojson,
        territory_geojson=terr_geojson if include_territory_geojson else None,
        processing=processing,
        territory=territory,
        duplicate=duplicate,
    )


def _find_existing(db: Session, user_id: int, client_run_id: str | None) -> Run | None:
    if not client_run_id:
        return None
    return (
        db.query(Run)
        .filter(Run.user_id == user_id, Run.client_run_id == client_run_id)
        .first()
    )


@router.post("", response_model=RunResponse)
def create_run(
    payload: RunCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = _find_existing(db, current_user.id, payload.client_run_id)
    if existing is not None:
        return _run_response(db, existing, duplicate=True)

    run = Run(
        user_id=current_user.id,
        duration_seconds=payload.duration_seconds,
        client_run_id=payload.client_run_id,
        started_at=_as_utc(payload.started_at),
        ended_at=_as_utc(payload.ended_at),
        client_distance_km=(
            payload.client_distance_km
            if payload.client_distance_km is not None
            else payload.distance_km
        ),
    )

    raw_fixes: list[RawFix] | None = None
    store_fixes = False
    raw_points: list[tuple[float, float]] = []
    legacy_coords = [
        c for c in (payload.route_coordinates or [])
    ]

    if payload.fixes is not None:
        raw_fixes = [
            RawFix(
                lat=f.lat,
                lng=f.lng,
                t=_as_utc(f.t).timestamp(),
                accuracy_m=f.accuracy_m,
                speed_mps=f.speed_mps,
                heading_deg=f.heading_deg,
                altitude_m=f.altitude_m,
            )
            for f in payload.fixes
        ]
        store_fixes = True
        raw_points = [(f.lat, f.lng) for f in payload.fixes]
    elif len(legacy_coords) >= 2:
        raw_fixes = _legacy_fixes(legacy_coords)
        raw_points = [(c[0], c[1]) for c in legacy_coords]

    result = None
    segments: list[list[tuple[float, float]]] = []
    quality = "unverified"

    if raw_fixes is not None:
        result = process_track(raw_fixes, TrackConfig())
        quality = result.quality if store_fixes else "unverified"
        for seg in result.segments:
            pts = [(result.fixes[i].lat, result.fixes[i].lng) for i in seg.fix_indices]
            segments.append(pts)

        run.distance_km = result.distance_m / 1000.0
        run.raw_distance_km = result.raw_distance_m / 1000.0
        run.uncertain_distance_m = result.uncertain_distance_m
        run.accepted_fix_count = result.accepted_count
        run.rejected_fix_count = result.rejected_count
        run.gap_count = result.gap_count
        run.algorithm_version = result.algorithm_version
        if store_fixes:
            run.moving_time_s = result.moving_time_s
            run.avg_speed = (
                run.distance_km / (result.moving_time_s / 3600.0)
                if result.moving_time_s and result.moving_time_s > 0
                else 0.0
            )
        else:
            # Synthetic timestamps mean no real moving time; use the phone's timer.
            run.moving_time_s = None
            run.avg_speed = (
                run.distance_km / (payload.duration_seconds / 3600.0)
                if payload.duration_seconds > 0
                else 0.0
            )
    else:
        # Scalar-only legacy payload: keep the client's numbers, award nothing.
        run.distance_km = payload.distance_km or 0.0
        run.avg_speed = payload.avg_speed or 0.0
        run.algorithm_version = ALGORITHM_VERSION

    run.quality = quality
    run.status = "processed" if raw_fixes is not None else "unprocessed"
    run.processed_at = datetime.now(timezone.utc)

    raw_ewkt = _raw_route_ewkt(raw_points) if raw_points else None

    try:
        db.add(run)
        db.flush()
    except IntegrityError:
        # Same (user, client_run_id) saved by a concurrent request.
        db.rollback()
        existing = _find_existing(db, current_user.id, payload.client_run_id)
        if existing is None:
            raise
        return _run_response(db, existing, duplicate=True)

    if store_fixes and result is not None and payload.fixes:
        rows = []
        for seq, (f, pf) in enumerate(zip(payload.fixes, result.fixes)):
            rows.append(
                {
                    "run_id": run.id,
                    "seq": seq,
                    "latitude": f.lat,
                    "longitude": f.lng,
                    "recorded_at": _as_utc(f.t),
                    "horizontal_accuracy_m": f.accuracy_m,
                    "reported_speed_mps": f.speed_mps,
                    "heading_deg": f.heading_deg,
                    "altitude_m": f.altitude_m,
                    "accepted": bool(pf.accepted),
                    "rejection_reason": pf.rejection_reason,
                    "segment_id": pf.segment_id,
                }
            )
        db.bulk_insert_mappings(GpsFix, rows)

    territory_result = {
        "kind": "none", "reason": "no route to award",
        "route_ewkt": None, "corridor_hex": None, "awarded_hex": None,
        "observed_area_sq_m": 0.0, "awarded_area_sq_m": 0.0,
    }
    if raw_fixes is not None:
        territory_result = claim_territory(
            db,
            user_id=current_user.id,
            segments=segments,
            quality=quality,
            distance_m=run.distance_km * 1000.0,
            uncertain_distance_m=run.uncertain_distance_m or 0.0,
        )
    db.execute(
            text(
                """
                UPDATE runs SET
                    route_geom = CASE WHEN :raw IS NULL THEN NULL
                                           ELSE ST_GeomFromEWKT(:raw) END,
                    processed_route_geom = CASE WHEN :route IS NULL THEN NULL
                                           ELSE ST_GeomFromEWKT(:route) END,
                    observed_corridor_geom = CASE WHEN :corr IS NULL THEN NULL
                                           ELSE ST_GeomFromEWKB(decode(:corr, 'hex')) END,
                    awarded_geom = CASE WHEN :awd IS NULL THEN NULL
                                           ELSE ST_GeomFromEWKB(decode(:awd, 'hex')) END,
                    observed_area_sq_m = :oa,
                    awarded_area_sq_m = :aa,
                    territory_kind = :kind
                WHERE id = :id
                """
            ),
            {
                "raw": raw_ewkt,
                "route": territory_result["route_ewkt"],
                "corr": territory_result["corridor_hex"],
                "awd": territory_result["awarded_hex"],
                "oa": territory_result["observed_area_sq_m"],
                "aa": territory_result["awarded_area_sq_m"],
                "kind": territory_result["kind"],
                "id": run.id,
            },
    )

    db.commit()
    db.refresh(run)
    return _run_response(db, run, reason=territory_result["reason"])


@router.get("", response_model=list[RunResponse])
def get_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runs = (
        db.query(Run)
        .filter(Run.user_id == current_user.id)
        .order_by(Run.id.desc())
        .all()
    )
    return [_run_response(db, run, include_territory_geojson=False) for run in runs]
