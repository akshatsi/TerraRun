"""
Run service — process GPS tracks, compute metrics, save runs.
"""

import math
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import GpsPoint, Run
from app.utils.geo import coords_to_linestring_wkt


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in metres between two GPS coordinates."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_distance(points: list[dict]) -> float:
    """Sum haversine distances between consecutive GPS points."""
    total = 0.0
    for i in range(1, len(points)):
        total += haversine(
            points[i - 1]["lat"], points[i - 1]["lng"],
            points[i]["lat"], points[i]["lng"],
        )
    return total


def compute_duration(started_at: datetime, ended_at: datetime) -> int:
    """Duration in seconds."""
    return int((ended_at - started_at).total_seconds())


def compute_avg_pace(distance_m: float, duration_s: int) -> float | None:
    """Average pace in min/km. Returns None if distance is 0."""
    if distance_m == 0:
        return None
    return (duration_s / 60) / (distance_m / 1000)


async def create_run(
    db: AsyncSession,
    user_id,
    started_at: datetime,
    ended_at: datetime,
    gps_points_data: list[dict],
) -> Run:
    """
    Create a run record from raw GPS points.
    1. Compute distance, duration, pace.
    2. Store LINESTRING polyline.
    3. Store raw GPS points.
    """
    distance = compute_distance(gps_points_data)
    duration = compute_duration(started_at, ended_at)
    pace = compute_avg_pace(distance, duration)

    # Build coordinate list as (lng, lat) for PostGIS
    coords = [(p["lng"], p["lat"]) for p in gps_points_data]
    polyline_wkt = coords_to_linestring_wkt(coords)

    run = Run(
        user_id=user_id,
        started_at=started_at,
        ended_at=ended_at,
        distance_m=round(distance, 2),
        duration_s=duration,
        avg_pace=round(pace, 2) if pace else None,
        status="completed",
    )

    # Set polyline geometry using raw SQL expression
    if polyline_wkt:
        from sqlalchemy import text
        from geoalchemy2.functions import ST_GeomFromText
        run.polyline = ST_GeomFromText(polyline_wkt, 4326)

    db.add(run)
    await db.flush()

    # Save raw GPS points
    for p in gps_points_data:
        gps_point = GpsPoint(
            run_id=run.id,
            lat=p["lat"],
            lng=p["lng"],
            altitude=p.get("altitude"),
            timestamp=p["timestamp"],
        )
        db.add(gps_point)

    await db.flush()
    await db.refresh(run)
    return run
