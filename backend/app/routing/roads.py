"""Road data for route suggestions: Overpass client, filter, tile cache.

See docs/route-suggestions.md. Roads come from OpenStreetMap, keep only the
allowed classes, and are cached in PostGIS by 0.01 degree tile for 30 days.
Tests pass a fake `fetcher` so nothing touches the network.
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from math import cos, floor, radians
from typing import Callable, Iterable

import httpx
from shapely.geometry import LineString
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import RoadTile
from app.models import RoadWay as RoadWayRow
from app.routing import RoadWay

log = logging.getLogger(__name__)

# Public Overpass servers are often busy or down, so several are tried in
# order. OVERPASS_URL (comma-separated) replaces this list.
DEFAULT_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
USER_AGENT = "TerraRun/1.0 (route suggestions; student project)"
TIMEOUT_S = 30.0          # per server
TOTAL_BUDGET_S = 60.0     # across all servers, so a request never hangs for minutes
TILE_DEG = 0.01
CACHE_DAYS = 30
M_PER_DEG_LAT = 111_320.0

ALLOWED_HIGHWAYS = frozenset(
    {"trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
     "living_street", "service"}
    | {f"{c}_link" for c in ("trunk", "primary", "secondary", "tertiary")}
)
BLOCKED_ACCESS = frozenset({"private", "no"})

# A fetcher takes (south, west, north, east) and returns raw Overpass elements.
Fetcher = Callable[[tuple[float, float, float, float]], list[dict]]


class RoadDataUnavailable(Exception):
    """Roads could not be fetched and none are cached for the area."""


# --- Overpass client -------------------------------------------------------

def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return f"[out:json][timeout:25];way[highway]({s:.6f},{w:.6f},{n:.6f},{e:.6f});out tags geom;"


def overpass_urls() -> list[str]:
    configured = os.getenv("OVERPASS_URL", "")
    urls = [u.strip() for u in configured.split(",") if u.strip()]
    return urls or list(DEFAULT_OVERPASS_URLS)


def overpass_fetch(bbox: tuple[float, float, float, float]) -> list[dict]:
    """Raw way elements for the box, from the first Overpass server that answers."""
    deadline = time.monotonic() + TOTAL_BUDGET_S
    errors = []
    for url in overpass_urls():
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            break
        try:
            resp = httpx.post(
                url,
                data={"data": overpass_query(bbox)},
                headers={"User-Agent": USER_AGENT},
                timeout=min(TIMEOUT_S, remaining),
            )
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
            log.warning("Overpass server failed, trying the next one: %s: %s", url, exc)
    raise httpx.HTTPError("All Overpass servers failed: " + "; ".join(errors))


# --- Filter and conversion -------------------------------------------------

def is_allowed_way(tags: dict) -> bool:
    """True for a main road a runner may be sent along."""
    highway = tags.get("highway")
    if highway not in ALLOWED_HIGHWAYS:
        return False
    if highway == "service" and "service" in tags:
        return False
    if tags.get("access") in BLOCKED_ACCESS:
        return False
    if tags.get("area") == "yes":
        return False
    return True


def element_to_road(element: dict) -> RoadWay | None:
    """RoadWay for an Overpass way element, or None if it is filtered out."""
    if element.get("type", "way") != "way":
        return None
    tags = element.get("tags") or {}
    if not is_allowed_way(tags):
        return None
    points = [(float(p["lat"]), float(p["lon"])) for p in element.get("geometry") or []
              if p and "lat" in p and "lon" in p]
    if len(points) < 2:
        return None
    return RoadWay(osm_id=int(element["id"]), highway=tags["highway"], points=points)


def filter_roads(elements: Iterable[dict]) -> list[RoadWay]:
    roads = (element_to_road(e) for e in elements)
    return [r for r in roads if r is not None]


# --- Tiles -----------------------------------------------------------------

def tile_index(lat: float, lng: float) -> tuple[int, int]:
    """(row, col) of the tile holding the point."""
    return floor(lat / TILE_DEG + 1e-9), floor(lng / TILE_DEG + 1e-9)


def tile_key_for(lat: float, lng: float) -> str:
    row, col = tile_index(lat, lng)
    return f"{row}_{col}"


def parse_tile_key(key: str) -> tuple[int, int]:
    row, col = key.split("_")
    return int(row), int(col)


def tile_bbox(key: str) -> tuple[float, float, float, float]:
    """(south, west, north, east) of a tile."""
    row, col = parse_tile_key(key)
    return (row * TILE_DEG, col * TILE_DEG, (row + 1) * TILE_DEG, (col + 1) * TILE_DEG)


def circle_bbox(center: tuple[float, float], radius_m: float) -> tuple[float, float, float, float]:
    lat, lng = center
    dlat = radius_m / M_PER_DEG_LAT
    dlng = radius_m / (M_PER_DEG_LAT * max(cos(radians(lat)), 0.01))
    return lat - dlat, lng - dlng, lat + dlat, lng + dlng


def tiles_covering(center: tuple[float, float], radius_m: float) -> list[str]:
    """Keys of every tile touched by the circle's bounding box."""
    s, w, n, e = circle_bbox(center, radius_m)
    r0, c0 = tile_index(s, w)
    r1, c1 = tile_index(n, e)
    return [f"{r}_{c}" for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]


# --- Cache -----------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _store(db: Session, keys: list[str], roads: list[RoadWay], now: datetime) -> None:
    """Replace the cached roads of `keys` and mark those tiles fetched."""
    db.execute(delete(RoadWayRow).where(RoadWayRow.tile_key.in_(keys)))
    rows = []
    for road in roads:
        line = LineString([(lng, lat) for lat, lng in road.points])
        rows.append({
            "osm_id": road.osm_id,
            "highway": road.highway,
            "geom": f"SRID=4326;{line.wkt}",
            "tile_key": tile_key_for(*road.points[0]),
            "fetched_at": now,
        })
    # An OSM way can come back from two neighbouring tiles; the last copy wins.
    unique = {r["osm_id"]: r for r in rows}
    if unique:
        stmt = pg_insert(RoadWayRow).values(list(unique.values()))
        stmt = stmt.on_conflict_do_update(
            index_elements=["osm_id"],
            set_={c: stmt.excluded[c] for c in ("highway", "geom", "tile_key", "fetched_at")},
        )
        db.execute(stmt)
    tiles = pg_insert(RoadTile).values([{"tile_key": k, "fetched_at": now} for k in keys])
    db.execute(tiles.on_conflict_do_update(
        index_elements=["tile_key"], set_={"fetched_at": tiles.excluded.fetched_at}
    ))
    db.commit()


def get_roads(
    db: Session,
    center: tuple[float, float],
    radius_m: float,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
) -> list[RoadWay]:
    """Allowed roads within radius_m of center (lat, lng).

    Tiles covering the circle that are missing or older than 30 days are
    fetched in one request. If that fails, cached tiles are used; with no
    cached tile at all, raises RoadDataUnavailable.
    """
    fetcher = fetcher or overpass_fetch
    now = now or _now()
    keys = tiles_covering(center, radius_m)
    fresh_after = now - timedelta(days=CACHE_DAYS)

    have = dict(db.execute(
        select(RoadTile.tile_key, RoadTile.fetched_at).where(RoadTile.tile_key.in_(keys))
    ).all())
    todo = [k for k in keys if k not in have or have[k] < fresh_after]

    if todo:
        boxes = [tile_bbox(k) for k in todo]
        bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))
        try:
            roads = filter_roads(fetcher(bbox))
        except Exception as exc:  # network, HTTP, bad JSON: all mean "no fresh data"
            log.warning("Overpass fetch failed: %s", exc)
            if not have:
                raise RoadDataUnavailable(
                    "Road data is unavailable right now. Try again soon."
                ) from exc
        else:
            _store(db, todo, roads, now)

    return _load(db, center, radius_m)


def _load(db: Session, center: tuple[float, float], radius_m: float) -> list[RoadWay]:
    lat, lng = center
    s, w, n, e = circle_bbox(center, radius_m)
    rows = db.execute(
        select(RoadWayRow.osm_id, RoadWayRow.highway, func.ST_AsGeoJSON(RoadWayRow.geom))
        .where(
            RoadWayRow.geom.op("&&")(func.ST_MakeEnvelope(w, s, e, n, 4326)),
            func.ST_DWithin(
                text("road_ways.geom::geography"),
                text("ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography").bindparams(
                    lng=lng, lat=lat),
                radius_m,
            ),
        )
    ).all()
    out = []
    for osm_id, highway, gj in rows:
        coords = json.loads(gj)["coordinates"]
        out.append(RoadWay(osm_id=osm_id, highway=highway,
                           points=[(c[1], c[0]) for c in coords]))
    return out
