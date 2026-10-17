"""
Territory capture using PostGIS. See docs/gps-accuracy.md, section 4.

1. ``build_territory_shape`` (app.gps.territory_shape) decides what a run
   earns from its accepted segments: a LOOP (only the enclosed area), a ROUTE
   (a flat-ended strip 3 m each side of the road travelled) or NONE. Segments
   are never joined across a gap.
2. This module adds the rules that need the run's quality and distance:
   nothing is awarded when the quality is "poor" or the accepted distance is
   under MIN_AWARD_DISTANCE_M, and the kind is then "none".
3. Otherwise the shape is cut out of every rival's territory (a rival left
   with under MIN_TERRITORY_AREA_SQ_M is deleted) and merged into the runner's
   own. Stored geometries are always (Multi)Polygon.
4. Areas are ST_Area(geom::geography), in square metres.
"""

import json

from shapely import wkb
from shapely.geometry import LineString, MultiLineString
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.gps.territory_shape import build_territory_shape
from app.models import Territory

MIN_AWARD_DISTANCE_M = 50    # shorter accepted distance earns nothing
SRID_WGS84 = 4326
MIN_TERRITORY_AREA_SQ_M = 1.0  # a rival's remainder below this is deleted


def build_multilinestring(segments: list[list[tuple[float, float]]]) -> MultiLineString | None:
    """Segments of (lat, lng) points -> MultiLineString in (lng, lat) order.

    Segments with fewer than two points are skipped. Returns None if none remain.
    """
    lines = [
        LineString([(lng, lat) for lat, lng in seg])
        for seg in segments
        if len(seg) >= 2
    ]
    if not lines:
        return None
    return MultiLineString(lines)


def multilinestring_ewkt(mls: MultiLineString) -> str:
    return f"SRID={SRID_WGS84};{mls.wkt}"


def user_territory_summary(
    db: Session, user_id: int, with_geojson: bool = True
) -> tuple[float, dict | None]:
    """Return (total area in m2, GeoJSON) of the user's territory."""
    geo = "ST_AsGeoJSON(geom)" if with_geojson else "NULL"
    row = db.execute(
        text(f"SELECT area_sq_m, {geo} FROM territories WHERE user_id = :u"),
        {"u": user_id},
    ).first()
    if row is None:
        return 0.0, None
    return float(row[0] or 0.0), (json.loads(row[1]) if row[1] else None)


def _areal_hex(db: Session, geom) -> tuple[str | None, float]:
    """Shapely geometry -> (hex EWKB of its valid polygon part, area in m2)."""
    if geom is None or geom.is_empty:
        return None, 0.0
    row = db.execute(
        text(
            """
            SELECT ST_AsHexEWKB(g), ST_Area(g::geography)
            FROM (
                SELECT ST_CollectionExtract(
                    ST_MakeValid(ST_GeomFromEWKB(decode(:h, 'hex'))), 3
                ) AS g
            ) q
            """
        ),
        {"h": wkb.dumps(geom, hex=True, srid=SRID_WGS84)},
    ).first()
    if row is None or row[0] is None:
        return None, 0.0
    area = float(row[1] or 0.0)
    if area <= 0.0:
        return None, 0.0
    return row[0], area


def award_run(
    db: Session,
    user_id: int,
    segments: list[list[tuple[float, float]]],
    quality: str,
    distance_m: float,
    uncertain_distance_m: float = 0.0,
) -> dict:
    """Build the shape for one run and award it. The caller commits.

    Returns a dict with:
        kind                  "loop" | "route" | "none"
        reason                short explanation
        route_ewkt            EWKT of the processed MultiLineString, or None
        corridor_hex          hex EWKB of the shape before rival handling, or None
        awarded_hex           hex EWKB of the awarded geometry, or None
        observed_area_sq_m
        awarded_area_sq_m
    """
    mls = build_multilinestring(segments)
    shape = build_territory_shape(segments, uncertain_distance_m)
    corridor_hex, observed_area = _areal_hex(db, shape.geometry)

    kind, reason = shape.kind, shape.reason
    if quality == "poor":
        kind, reason = "none", "GPS quality too poor to award territory"
    elif distance_m < MIN_AWARD_DISTANCE_M:
        kind, reason = "none", f"under {MIN_AWARD_DISTANCE_M} m accepted distance"
    elif corridor_hex is None:
        kind = "none"

    result = {
        "kind": kind,
        "reason": reason,
        "route_ewkt": multilinestring_ewkt(mls) if mls is not None else None,
        "corridor_hex": corridor_hex,
        "awarded_hex": None,
        "observed_area_sq_m": observed_area,
        "awarded_area_sq_m": 0.0,
    }
    if kind != "none" and corridor_hex:
        award_polygon(db, user_id, corridor_hex)
        result["awarded_hex"] = corridor_hex
        result["awarded_area_sq_m"] = observed_area
    return result


def claim_territory(
    db: Session,
    user_id: int,
    segments: list[list[tuple[float, float]]],
    quality: str,
    distance_m: float,
    uncertain_distance_m: float = 0.0,
) -> dict:
    """award_run plus the user's total area and GeoJSON afterwards."""
    result = award_run(db, user_id, segments, quality, distance_m, uncertain_distance_m)
    total, geojson = user_territory_summary(db, user_id)
    result["total_area_sq_m"] = total
    result["territory_geojson"] = geojson
    return result


def award_polygon(db: Session, user_id: int, awarded_hex: str) -> None:
    """Cut the polygon out of rivals and merge it into the user's territory."""
    params = {"h": awarded_hex, "u": user_id}
    awarded = "ST_GeomFromEWKB(decode(:h, 'hex'))"

    # Rivals: subtract, keep only areal parts, recompute area, drop the empty.
    db.execute(
        text(
            f"""
            UPDATE territories
            SET geom = ST_CollectionExtract(ST_MakeValid(ST_Difference(geom, {awarded})), 3),
                updated_at = now()
            WHERE user_id <> :u AND geom && {awarded} AND ST_Intersects(geom, {awarded})
            """
        ),
        params,
    )
    db.execute(
        text(
            f"""
            UPDATE territories SET area_sq_m = ST_Area(geom::geography)
            WHERE user_id <> :u AND geom && {awarded} AND NOT ST_IsEmpty(geom)
            """
        ),
        params,
    )
    # Drop what is left of a rival when nothing real remains (empty, or float
    # noise from the cut).
    db.execute(
        text(
            "DELETE FROM territories WHERE user_id <> :u "
            "AND (ST_IsEmpty(geom) OR area_sq_m < :min_area)"
        ),
        {"u": user_id, "min_area": MIN_TERRITORY_AREA_SQ_M},
    )

    own = db.query(Territory.id).filter(Territory.user_id == user_id).first()
    if own is None:
        db.execute(
            text(
                f"""
                INSERT INTO territories (user_id, geom, area_sq_m)
                VALUES (:u, ST_CollectionExtract(ST_MakeValid({awarded}), 3),
                        ST_Area(ST_CollectionExtract(ST_MakeValid({awarded}), 3)::geography))
                """
            ),
            params,
        )
    else:
        db.execute(
            text(
                f"""
                UPDATE territories
                SET geom = ST_CollectionExtract(ST_MakeValid(ST_Union(geom, {awarded})), 3),
                    updated_at = now()
                WHERE user_id = :u
                """
            ),
            params,
        )
        db.execute(
            text("UPDATE territories SET area_sq_m = ST_Area(geom::geography) WHERE user_id = :u"),
            params,
        )
    db.flush()
