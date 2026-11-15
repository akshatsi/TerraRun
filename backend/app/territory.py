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
5. Before step 1 the caller turns the accepted segments into a clean track
   (``clean_segments``, docs/gps-accuracy.md section 6). After a run is merged,
   land walled in by the runner's own territory is awarded too
   (``app.gps.enclosure``, section 7).
"""

import json
import logging

from shapely import wkb
from shapely.geometry import LineString, MultiLineString
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.gps.clean_track import CleanTrack, clean_track
from app.gps.enclosure import enclosed_by
from app.gps.territory_shape import build_territory_shape
from app.models import Territory
from app.routing.roads import RoadDataUnavailable, expand_bbox, get_walk_ways

log = logging.getLogger(__name__)

MIN_AWARD_DISTANCE_M = 50    # shorter accepted distance earns nothing
SRID_WGS84 = 4326
MIN_TERRITORY_AREA_SQ_M = 1.0  # a rival's remainder below this is deleted
WAYS_MARGIN_M = 50.0           # walkable ways are loaded this far around a run


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


def clean_segments(
    db: Session,
    segments: list[list[tuple[float, float]]],
    accuracies: list[list[float | None]] | None = None,
    fetcher=None,
    one_segment: bool = False,
    commit: bool = True,
) -> CleanTrack:
    """Clean a run's accepted segments against the walkable ways around it.

    Never raises because of road data: if the ways cannot be loaded the track is
    only smoothed, and if cleaning itself fails the raw segments are returned
    (method "raw"). `one_segment` joins the segments first, for old runs whose
    timestamps were invented. `commit=False` keeps the road cache in the
    caller's transaction (reprocess).
    """
    if accuracies is None or len(accuracies) != len(segments) or any(
        len(a) != len(s) for a, s in zip(accuracies, segments)
    ):
        accuracies = [[None] * len(seg) for seg in segments]
    if one_segment and len(segments) > 1:
        segments = [[p for seg in segments for p in seg]]
        accuracies = [[a for acc in accuracies for a in acc]]

    ways = []
    points = [p for seg in segments for p in seg]
    if points:
        lats, lngs = [p[0] for p in points], [p[1] for p in points]
        bbox = expand_bbox((min(lats), min(lngs), max(lats), max(lngs)), WAYS_MARGIN_M)
        try:
            ways = get_walk_ways(db, bbox, fetcher, commit=commit)
        except RoadDataUnavailable:
            log.info("No road data for this run; smoothing only")
        except Exception:
            if not commit:
                raise
            log.exception("Loading walkable ways failed; smoothing only")
            db.rollback()
    try:
        clean = clean_track(segments, accuracies, ways)
    except Exception:
        log.exception("clean_track failed; using the accepted fixes as they are")
        return CleanTrack(segments=segments, method="raw", matched_fraction=0.0,
                          notes="clean_track failed")
    # Cleaning must never cost a runner a loop: a small loop with few fixes can
    # be smoothed below the loop minimums. Then the accepted fixes are kept.
    if build_territory_shape(clean.segments).kind != "loop" and \
            build_territory_shape(segments).kind == "loop":
        return CleanTrack(segments=segments, method="raw", matched_fraction=0.0,
                          notes="kept the accepted fixes: cleaning lost the loop")
    return clean


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
        awarded_hex           hex EWKB of the awarded geometry (shape plus any
                              enclosed land), or None
        observed_area_sq_m    area of the shape before rival handling
        awarded_area_sq_m     area awarded: the shape plus enclosed_area_sq_m
        enclosed_area_sq_m    land walled in by the runner's territory, awarded too
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
        "enclosed_area_sq_m": 0.0,
    }
    if kind != "none" and corridor_hex:
        filled_hex, filled_area = award_polygon(db, user_id, corridor_hex)
        result["awarded_hex"] = corridor_hex
        result["awarded_area_sq_m"] = observed_area
        if filled_hex:
            result["awarded_hex"] = _union_hex(db, corridor_hex, filled_hex)
            result["awarded_area_sq_m"] = observed_area + filled_area
            result["enclosed_area_sq_m"] = filled_area
            result["reason"] = f"{reason}; {filled_area:,.0f} m² enclosed by your territory"
            log.info("User %s: run filled %.0f m2 enclosed by own territory", user_id, filled_area)
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


def _union_hex(db: Session, a_hex: str, b_hex: str) -> str:
    return db.execute(
        text(
            "SELECT ST_AsHexEWKB(ST_CollectionExtract(ST_MakeValid(ST_Union("
            "ST_GeomFromEWKB(decode(:a, 'hex')), ST_GeomFromEWKB(decode(:b, 'hex')))), 3))"
        ),
        {"a": a_hex, "b": b_hex},
    ).scalar()


def award_polygon(
    db: Session, user_id: int, awarded_hex: str, fill_enclosed: bool = True
) -> tuple[str | None, float]:
    """Cut the polygon out of rivals and merge it into the user's territory.

    Then land walled in by the user's territory is awarded the same way (section
    7), once. Returns (hex EWKB, area in m2) of that filled land, or (None, 0.0).
    """
    _merge_polygon(db, user_id, awarded_hex)
    if not fill_enclosed:
        return None, 0.0
    row = db.execute(
        text("SELECT ST_AsHexEWKB(geom) FROM territories WHERE user_id = :u"), {"u": user_id}
    ).first()
    if row is None or row[0] is None:
        return None, 0.0
    filled = enclosed_by(wkb.loads(row[0], hex=True))
    filled_hex, filled_area = _areal_hex(db, filled)
    if filled_hex is None:
        return None, 0.0
    _merge_polygon(db, user_id, filled_hex)
    return filled_hex, filled_area


def _merge_polygon(db: Session, user_id: int, awarded_hex: str) -> None:
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
