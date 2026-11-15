"""Upload, award and reprocess wiring for clean tracks, the walkable-way cache
and enclosure fill (docs/gps-accuracy.md sections 6 and 7).

`clean_track` is replaced by a small fake where a test is about the wiring, so
these tests do not depend on how well the real cleaner snaps.
"""
import json
from datetime import datetime, timezone
from math import cos, radians

import pytest
from sqlalchemy import text

from app.database import SessionLocal, engine
from app.gps.clean_track import CleanTrack
from app.routes.run_routes import get_walk_fetcher
from app.routing.roads import ROAD_DATA_VERSION, get_roads, get_walk_ways
from setup_postgis import setup_database
from tests.conftest import LAT0, LNG0, M_PER_DEG_LAT, run_payload, walk_fixes

M_PER_DEG_LNG = M_PER_DEG_LAT * cos(radians(LAT0))


def ll(x, y):
    return LAT0 + y / M_PER_DEG_LAT, LNG0 + x / M_PER_DEG_LNG


def element(osm_id, pts_m, **tags):
    tags.setdefault("highway", "residential")
    return {"type": "way", "id": osm_id, "tags": tags,
            "geometry": [{"lat": ll(x, y)[0], "lon": ll(x, y)[1]} for x, y in pts_m]}


def scalar(sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


class FakeClean:
    """Replaces clean_track: each segment becomes a straight line first->last."""

    def __init__(self):
        self.calls = []

    def __call__(self, segments, accuracies, ways, config=None):
        self.calls.append({"segments": segments, "accuracies": accuracies, "ways": ways})
        out = [[seg[0], seg[-1]] if len(seg) >= 2 else list(seg) for seg in segments]
        return CleanTrack(segments=out, method="matched" if ways else "smoothed",
                          matched_fraction=1.0 if ways else 0.0, notes=[])


@pytest.fixture()
def fake_clean(monkeypatch):
    f = FakeClean()
    monkeypatch.setattr("app.territory.clean_track", f)
    return f


@pytest.fixture()
def walk_fetcher(client):
    from app.main import app
    holder = {"calls": [], "fail": False,
              "elements": [element(10, [(-50, 0), (300, 0)], highway="footway"),
                           element(11, [(-50, 20), (300, 20)], highway="residential")]}

    def fetch(bbox):
        holder["calls"].append(bbox)
        if holder["fail"]:
            raise RuntimeError("overpass down")
        return holder["elements"]

    app.dependency_overrides[get_walk_fetcher] = lambda: fetch
    yield holder
    app.dependency_overrides.pop(get_walk_fetcher, None)


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def post(client, auth, body):
    r = client.post("/runs", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


# --- upload ----------------------------------------------------------------

def test_upload_uses_cleaned_line_and_stores_method(client, auth, fake_clean, walk_fetcher):
    fixes = walk_fixes([(0, 0), (60, 4), (120, -3), (200, 0)])
    b = post(client, auth, run_payload(fixes))
    assert len(walk_fetcher["calls"]) == 1
    assert len(fake_clean.calls) == 1
    assert {w.osm_id for w in fake_clean.calls[0]["ways"]} == {10, 11}  # footway included
    assert all(a is not None for a in fake_clean.calls[0]["accuracies"][0])
    assert b["route_geojson"]["type"] == "MultiLineString"
    coords = b["route_geojson"]["coordinates"]
    assert len(coords) == 1 and len(coords[0]) == 2          # the cleaned line, not the raw fixes
    assert scalar("SELECT clean_method FROM runs") == "matched"
    assert scalar("SELECT matched_fraction FROM runs") == pytest.approx(1.0)
    # distance is the engine's, not the clean line's
    assert b["distance_km"] == pytest.approx(0.2, rel=0.1)
    assert b["territory"]["awarded_area_sq_m"] > 0
    # the cache holds the footway but flags it as not a main road
    assert scalar("SELECT is_main FROM road_ways WHERE osm_id=10") is False
    assert scalar("SELECT is_main FROM road_ways WHERE osm_id=11") is True


def test_upload_succeeds_when_fetcher_raises(client, auth, fake_clean, walk_fetcher):
    walk_fetcher["fail"] = True
    b = post(client, auth, run_payload(walk_fixes([(0, 0), (200, 0)])))
    assert fake_clean.calls[0]["ways"] == []
    assert scalar("SELECT clean_method FROM runs") == "smoothed"
    assert b["territory"]["awarded_area_sq_m"] > 0
    assert scalar("SELECT count(*) FROM road_tiles") == 0     # failure caches nothing


def test_upload_survives_clean_track_crash(client, auth, monkeypatch):
    def boom(*a, **k):
        raise ValueError("bug")
    monkeypatch.setattr("app.territory.clean_track", boom)
    b = post(client, auth, run_payload(walk_fixes([(0, 0), (200, 0)])))
    assert scalar("SELECT clean_method FROM runs") == "raw"
    assert b["territory"]["awarded_area_sq_m"] > 0


def test_legacy_run_is_one_segment(client, auth, fake_clean):
    step = 15.0 / M_PER_DEG_LNG
    # A 600 m jump in the middle: the engine re-anchors and splits the track.
    coords = [[LAT0, LNG0 + i * step] for i in range(12)]
    coords += [[LAT0, LNG0 + (11 + 40) * step + i * step] for i in range(12)]
    post(client, auth, {"distance_km": 1.0, "duration_seconds": 200, "avg_speed": 10.0,
                        "route_coordinates": coords})
    assert len(fake_clean.calls) == 1
    assert len(fake_clean.calls[0]["segments"]) == 1


# --- enclosure -------------------------------------------------------------

def test_four_strips_enclose_the_interior(client, auth, fake_clean):
    legs = [[(-5, 0), (125, 0)], [(120, -5), (120, 105)],
            [(125, 100), (-5, 100)], [(0, 105), (0, -5)]]
    areas = []
    for leg in legs:
        b = post(client, auth, run_payload(walk_fixes(leg)))
        areas.append(b["territory"]["total_area_sq_m"])
    inside = "ST_Contains(geom, ST_SetSRID(ST_MakePoint(:x, :y), 4326))"
    lat, lng = ll(60, 50)
    assert scalar(f"SELECT {inside} FROM territories", x=lng, y=lat) is True
    # strips alone are ~4 * 120 * 6 m2; the interior is ~110 * 94 m2 more
    assert areas[3] - areas[2] > 8000
    assert areas[2] < 5000
    assert scalar("SELECT awarded_area_sq_m FROM runs WHERE id=4") > 8000
    assert "enclosed by your territory" in b["territory"]["reason"]
    assert scalar("SELECT GeometryType(geom) FROM territories") in ("POLYGON", "MULTIPOLYGON")


# --- road cache ------------------------------------------------------------

def test_suggestions_only_get_main_roads(db):
    els = [element(10, [(-50, 0), (300, 0)], highway="footway"),
           element(11, [(-50, 20), (300, 20)], highway="residential"),
           element(12, [(-50, 40), (300, 40)], highway="path"),
           element(13, [(-50, 60), (300, 60)], highway="residential", access="private")]
    walk = get_walk_ways(db, (LAT0 - 0.001, LNG0 - 0.001, LAT0 + 0.001, LNG0 + 0.004),
                         fetcher=lambda b: els)
    assert {w.osm_id for w in walk} == {10, 11, 12}
    calls = []
    roads = get_roads(db, (LAT0, LNG0), 300, fetcher=lambda b: calls.append(b) or els)
    assert {r.osm_id for r in roads} == {11}
    assert calls == []                                        # served from the cache


def test_old_tiles_refetched_for_walk_ways_but_not_for_roads(db):
    els = [element(10, [(-50, 0), (300, 0)], highway="footway"),
           element(11, [(-50, 20), (300, 20)], highway="residential")]
    box = (LAT0 - 0.001, LNG0 - 0.001, LAT0 + 0.001, LNG0 + 0.004)
    get_walk_ways(db, box, fetcher=lambda b: els)
    with engine.begin() as c:
        c.execute(text("UPDATE road_tiles SET version = 1"))
        c.execute(text("DELETE FROM road_ways WHERE osm_id = 10"))   # as if main-only
    calls = []
    get_roads(db, (LAT0, LNG0), 300, fetcher=lambda b: calls.append(b) or els)
    assert calls == []                                        # old tile fine for suggestions
    # refetch fails: the old data is used as it is
    def down(b):
        raise RuntimeError("down")
    assert {w.osm_id for w in get_walk_ways(db, box, fetcher=down)} == {11}
    assert scalar("SELECT min(version) FROM road_tiles") == 1
    # refetch works: footway appears and tiles are upgraded
    assert {w.osm_id for w in get_walk_ways(db, box, fetcher=lambda b: els)} == {10, 11}
    assert scalar("SELECT min(version) FROM road_tiles") == ROAD_DATA_VERSION


def test_setup_adds_road_columns_with_defaults():
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS road_ways, road_tiles"))
        c.execute(text("CREATE TABLE road_tiles (tile_key VARCHAR(24) PRIMARY KEY, "
                       "fetched_at TIMESTAMPTZ NOT NULL)"))
        c.execute(text("CREATE TABLE road_ways (osm_id BIGINT PRIMARY KEY, highway VARCHAR(32) "
                       "NOT NULL, geom geometry(LINESTRING,4326) NOT NULL, "
                       "tile_key VARCHAR(24) NOT NULL, fetched_at TIMESTAMPTZ NOT NULL)"))
        c.execute(text("INSERT INTO road_tiles VALUES ('1_1', now())"))
        c.execute(text("INSERT INTO road_ways VALUES (5, 'residential', "
                       "ST_GeomFromText('LINESTRING(0 0,1 1)',4326), '1_1', now())"))
    setup_database(engine)
    setup_database(engine)
    assert scalar("SELECT version FROM road_tiles") == 1
    assert scalar("SELECT is_main FROM road_ways") is True


# --- reprocess -------------------------------------------------------------

def snapshot():
    return {t: scalar(f"SELECT md5(coalesce(string_agg(x::text, ',' ORDER BY x::text), '')) "
                      f"FROM {t} x")
            for t in ("runs", "territories", "road_ways", "road_tiles")}


def test_reprocess_dry_run_writes_nothing_and_real_run_rederives(client, auth, fake_clean):
    import reprocess_territories as rp
    post(client, auth, run_payload(walk_fixes([(0, 0), (200, 0)])))
    step = 15.0 / M_PER_DEG_LNG
    post(client, auth, {"distance_km": 1.0, "duration_seconds": 200, "avg_speed": 10.0,
                        "route_coordinates": [[LAT0 + 0.003, LNG0 + i * step] for i in range(40)]})
    with engine.begin() as c:
        c.execute(text("UPDATE runs SET processed_route_geom = NULL, clean_method = NULL, "
                       "matched_fraction = NULL"))
    els = [element(10, [(-50, 0), (300, 0)], highway="footway")]
    before = snapshot()

    s = SessionLocal()
    try:
        lines = []
        summary = rp.reprocess(s, fetcher=lambda b: els, log=lines.append)
        s.rollback()                       # what --dry-run does
    finally:
        s.close()
    assert snapshot() == before            # runs, territories and the road cache untouched
    assert summary["runs"] == 2 and sum(summary["methods"].values()) == 2
    assert any("Will delete" in ln for ln in lines)
    assert sum("run " in ln and "matched" in ln for ln in lines) == 2

    assert rp.main(["--dry-run", "--offline"]) == 0
    assert snapshot() == before

    assert rp.main(["--offline"]) == 0
    assert scalar("SELECT count(*) FROM runs WHERE processed_route_geom IS NOT NULL") == 2
    assert scalar("SELECT count(*) FROM runs WHERE clean_method IS NOT NULL") == 2
    # the legacy run was cleaned as one segment
    assert len(fake_clean.calls[-1]["segments"]) == 1
    assert json.loads(scalar("SELECT ST_AsGeoJSON(processed_route_geom) FROM runs WHERE id=1"))


def test_cleaning_never_costs_a_loop(db, monkeypatch):
    """If the cleaned track is no longer a loop but the accepted fixes are, keep the fixes."""
    from app.territory import clean_segments

    square = [ll(x, y) for x, y in [(0, 0), (60, 0), (60, 60), (0, 60), (0, 0)]]
    shrunk = [ll(x, y) for x, y in [(0, 0), (20, 0), (20, 20)]]
    monkeypatch.setattr(
        "app.territory.clean_track",
        lambda segs, accs, ways: CleanTrack(segments=[shrunk], method="smoothed",
                                            matched_fraction=0.0, notes=""),
    )
    out = clean_segments(db, [square], fetcher=lambda bbox: [], commit=False)
    assert out.method == "raw"
    assert out.segments == [square]
