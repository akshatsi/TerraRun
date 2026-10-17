"""POST /runs and GET /runs against a real PostGIS."""
from math import cos, radians

import pytest
from sqlalchemy import text

from app.database import engine
from setup_postgis import setup_database
from tests.conftest import (
    LAT0, LNG0, M_PER_DEG_LAT, make_fixes, run_payload, square_loop_fixes, walk_fixes,
)


def post(client, auth, body):
    return client.post("/runs", json=body, headers=auth)


def db_scalar(sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def test_new_payload_end_to_end(client, auth):
    fixes = make_fixes(n=120, speed=3.0)  # 357 m
    r = post(client, auth, run_payload(fixes, client_distance_km=0.9))
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["duplicate"] is False
    assert b["distance_km"] == pytest.approx(0.357, rel=0.03)
    assert b["avg_speed"] == pytest.approx(3.0 * 3.6, rel=0.1)
    assert b["route_geojson"]["type"] == "MultiLineString"
    assert b["territory_geojson"] is not None
    p = b["processing"]
    assert p["quality"] in ("good", "fair")
    assert p["accepted_fixes"] + p["rejected_fixes"] == 120
    assert p["client_distance_km"] == 0.9
    assert p["algorithm_version"].startswith("gps-")
    t = b["territory"]
    assert t["observed_area_sq_m"] == pytest.approx(357 * 6, rel=0.05)
    assert t["awarded_area_sq_m"] == pytest.approx(t["observed_area_sq_m"])
    assert t["total_area_sq_m"] == pytest.approx(t["awarded_area_sq_m"])
    assert t["kind"] == "route" and t["reason"]

    # Stored state
    rid = b["id"]
    assert db_scalar("SELECT count(*) FROM gps_fixes WHERE run_id=:i", i=rid) == 120
    assert db_scalar("SELECT status FROM runs WHERE id=:i", i=rid) == "processed"
    assert db_scalar("SELECT GeometryType(route_geom) FROM runs WHERE id=:i", i=rid) == "LINESTRING"
    assert db_scalar("SELECT GeometryType(processed_route_geom) FROM runs WHERE id=:i", i=rid) == "MULTILINESTRING"
    assert db_scalar("SELECT ST_SRID(awarded_geom) FROM runs WHERE id=:i", i=rid) == 4326
    assert db_scalar("SELECT count(*) FROM gps_fixes WHERE run_id=:i AND accepted", i=rid) == p["accepted_fixes"]

    got = client.get("/runs", headers=auth).json()
    assert len(got) == 1 and got[0]["processing"]["quality"] == p["quality"]
    assert got[0]["route_geojson"]["type"] == "MultiLineString"
    assert got[0]["distance_km"] == b["distance_km"]
    assert got[0]["territory"]["kind"] == "route" and got[0]["territory"]["reason"]
    assert db_scalar("SELECT territory_kind FROM runs WHERE id=:i", i=rid) == "route"


def test_duplicate_is_idempotent(client, auth):
    body = run_payload(make_fixes(n=100), client_run_id="a" * 32)
    first = post(client, auth, body).json()
    area = db_scalar("SELECT area_sq_m FROM territories")
    second = post(client, auth, body)
    assert second.status_code == 200
    s = second.json()
    assert s["duplicate"] is True and s["id"] == first["id"]
    assert s["distance_km"] == first["distance_km"]
    assert db_scalar("SELECT area_sq_m FROM territories") == area
    assert db_scalar("SELECT count(*) FROM runs") == 1
    assert db_scalar("SELECT count(*) FROM gps_fixes") == 100


def test_same_client_id_other_user_is_separate(client, make_user):
    a, b = make_user("Alice"), make_user("Bob")
    body = run_payload(make_fixes(n=100), client_run_id="b" * 32)
    assert post(client, a, body).json()["duplicate"] is False
    assert post(client, b, body).json()["duplicate"] is False


def test_race_on_unique_constraint(client, auth, monkeypatch):
    from app.routes import run_routes
    body = run_payload(make_fixes(n=100), client_run_id="c" * 32)
    first = post(client, auth, body).json()
    # Hide the existing run from the first lookup so the insert hits the constraint.
    real = run_routes._find_existing
    calls = {"n": 0}

    def fake(db, uid, cid):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(db, uid, cid)

    monkeypatch.setattr(run_routes, "_find_existing", fake)
    r = post(client, auth, body)
    assert r.status_code == 200 and r.json()["duplicate"] is True
    assert r.json()["id"] == first["id"]
    assert db_scalar("SELECT count(*) FROM runs") == 1


def test_gap_run_has_two_lines_and_no_bridge(client, auth):
    dlat = 500.0 / M_PER_DEG_LAT
    a = make_fixes(n=100, speed=3.0)                              # 297 m
    b = make_fixes(lat=LAT0 + dlat, n=100, speed=3.0, t_start=160)  # 60 s gap
    r = post(client, auth, run_payload(a + b))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["processing"]["gap_count"] >= 1
    assert len(body["route_geojson"]["coordinates"]) == 2
    # A big gap makes the run "poor": nothing is awarded, but the two strips
    # are observed and are not joined across the gap.
    assert body["processing"]["quality"] == "poor"
    assert body["territory"]["kind"] == "none"
    assert body["territory"]["awarded_area_sq_m"] == 0
    assert body["territory"]["observed_area_sq_m"] == pytest.approx(2 * 297 * 6, rel=0.08)
    # Distance excludes the bridge (~500 m).
    assert body["distance_km"] == pytest.approx(0.594, rel=0.05)
    assert body["processing"]["uncertain_distance_m"] > 400


def test_poor_quality_awards_nothing(client, auth):
    fixes = make_fixes(n=100, accuracy=150.0)
    r = post(client, auth, run_payload(fixes))
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["processing"]["quality"] == "poor"
    assert b["territory"]["awarded_area_sq_m"] == 0
    assert b["territory"]["total_area_sq_m"] == 0
    assert b["territory"]["kind"] == "none"
    assert db_scalar("SELECT territory_kind FROM runs") == "none"
    assert db_scalar("SELECT count(*) FROM territories") == 0
    assert db_scalar("SELECT count(*) FROM runs") == 1


def test_under_50m_awards_nothing(client, auth):
    r = post(client, auth, run_payload(make_fixes(n=15, speed=3.0)))  # ~42 m
    b = r.json()
    assert 0 < b["distance_km"] < 0.05
    assert b["territory"]["awarded_area_sq_m"] == 0
    assert b["territory"]["kind"] == "none"
    assert db_scalar("SELECT count(*) FROM territories") == 0


def test_rival_loses_overlap(client, make_user):
    a, b = make_user("Alice"), make_user("Bob")
    ra = post(client, a, run_payload(make_fixes(n=100))).json()
    area_a = ra["territory"]["total_area_sq_m"]
    rb = post(client, b, run_payload(make_fixes(n=100))).json()
    # Bob ran the identical path: Alice is wiped out.
    assert rb["territory"]["awarded_area_sq_m"] > 0
    assert db_scalar("SELECT count(*) FROM territories WHERE user_id=1") == 0
    # Partial overlap
    c = make_user("Cara")
    post(client, c, run_payload(make_fixes(n=100)))
    shifted = LNG0 + 150.0 / (M_PER_DEG_LAT * cos(radians(LAT0)))
    post(client, a, run_payload(make_fixes(lng=shifted, n=100)))
    cara = db_scalar("SELECT area_sq_m FROM territories WHERE user_id=3")
    assert 0 < cara < area_a


def test_legacy_payload_with_coordinates(client, auth):
    step = 15.0 / (M_PER_DEG_LAT * cos(radians(LAT0)))
    coords = [[LAT0, LNG0 + i * step] for i in range(40)]  # 585 m
    r = post(client, auth, {
        "distance_km": 9.9, "duration_seconds": 200, "avg_speed": 10.0,
        "route_coordinates": coords,
    })
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["distance_km"] == pytest.approx(0.585, rel=0.05)  # server value, not 9.9
    assert b["processing"]["quality"] == "unverified"
    assert b["processing"]["client_distance_km"] == 9.9
    assert b["territory"]["awarded_area_sq_m"] == pytest.approx(585 * 6, rel=0.06)
    assert b["territory"]["kind"] == "route"
    assert db_scalar("SELECT territory_kind FROM runs") == "route"
    assert b["route_geojson"]["type"] == "MultiLineString"
    assert db_scalar("SELECT count(*) FROM gps_fixes") == 0


def test_legacy_scalar_only(client, auth):
    r = post(client, auth, {"distance_km": 3.2, "duration_seconds": 1000, "avg_speed": 11.5})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["distance_km"] == 3.2 and b["avg_speed"] == 11.5
    assert b["processing"]["quality"] == "unverified"
    assert b["territory"]["awarded_area_sq_m"] == 0
    assert b["territory"]["kind"] == "none"
    assert db_scalar("SELECT count(*) FROM territories") == 0
    assert client.get("/runs", headers=auth).json()[0]["distance_km"] == 3.2


def test_garbage_is_rejected(client, auth):
    ok = make_fixes(n=5)
    assert post(client, auth, {"duration_seconds": 10}).status_code == 422
    assert post(client, auth, run_payload(ok, duration_seconds=-1)).status_code == 422
    bad = [dict(ok[0], t="not a time")]
    assert post(client, auth, run_payload(bad)).status_code == 422
    assert post(client, auth, run_payload([dict(ok[0], lat="x")])).status_code == 422
    assert post(client, auth, run_payload(ok, client_run_id="x")).status_code == 422
    assert post(client, auth, {"duration_seconds": 5, "distance_km": 1, "route_coordinates": [[1.0]]}).status_code == 422
    huge = [ok[0]] * 100_001
    assert post(client, auth, run_payload(huge)).status_code == 422
    assert client.post("/runs", json=run_payload(ok)).status_code == 401
    assert db_scalar("SELECT count(*) FROM runs") == 0


def test_empty_fixes_saved_without_award(client, auth):
    r = post(client, auth, run_payload([], duration_seconds=30))
    assert r.status_code == 200, r.text
    assert r.json()["distance_km"] == 0
    assert r.json()["territory"]["awarded_area_sq_m"] == 0
    assert r.json()["territory"]["kind"] == "none"


def test_out_of_range_coordinates_do_not_crash(client, auth):
    fixes = make_fixes(n=40)
    fixes[10]["lat"] = 123.0
    r = post(client, auth, run_payload(fixes))
    assert r.status_code == 200, r.text


# --- territory kinds ----------------------------------------------------------

def test_closed_square_loop_awards_enclosed_area(client, auth):
    r = post(client, auth, run_payload(square_loop_fixes(100.0)))
    assert r.status_code == 200, r.text
    t = r.json()["territory"]
    assert t["kind"] == "loop"
    assert t["awarded_area_sq_m"] == pytest.approx(100 * 100, rel=0.05)  # not the ~2,400 m2 corridor
    assert t["total_area_sq_m"] == pytest.approx(t["awarded_area_sq_m"])
    assert db_scalar("SELECT territory_kind FROM runs") == "loop"
    assert db_scalar("SELECT GeometryType(awarded_geom) FROM runs") in ("POLYGON", "MULTIPOLYGON")
    assert db_scalar("SELECT ST_SRID(observed_corridor_geom) FROM runs") == 4326


def test_open_140m_route_awards_a_strip(client, auth):
    r = post(client, auth, run_payload(make_fixes(n=48, speed=3.0)))
    b = r.json()
    assert 0.13 < b["distance_km"] < 0.15
    assert b["territory"]["kind"] == "route"
    assert b["territory"]["awarded_area_sq_m"] == pytest.approx(840, rel=0.05)


def test_out_and_back_is_a_route(client, auth):
    fixes = walk_fixes([(0, 0), (100, 0), (0, 0)])
    b = post(client, auth, run_payload(fixes)).json()
    assert b["territory"]["kind"] == "route"
    assert b["territory"]["awarded_area_sq_m"] < 100 * 6 * 1.2


def test_loop_over_rival_strip_subtracts_and_keeps_polygons(client, make_user):
    a, b = make_user("Alice"), make_user("Bob")
    strip = walk_fixes([(-50, 50), (150, 50)])
    post(client, a, run_payload(strip))
    full = db_scalar("SELECT area_sq_m FROM territories WHERE user_id=1")
    rb = post(client, b, run_payload(square_loop_fixes(100.0))).json()
    assert rb["territory"]["kind"] == "loop"
    left = db_scalar("SELECT area_sq_m FROM territories WHERE user_id=1")
    assert left == pytest.approx(full - 100 * 6, rel=0.1)
    types = geometry_types()
    assert types <= {"POLYGON", "MULTIPOLYGON"}


# --- reprocess_territories.py ---------------------------------------------------

def geometry_types():
    with engine.connect() as c:
        return {r[0] for r in c.execute(text("SELECT GeometryType(geom) FROM territories"))}


def territory_state():
    with engine.connect() as c:
        return c.execute(text(
            "SELECT user_id, round(area_sq_m::numeric, 3), md5(ST_AsEWKB(geom)::text) "
            "FROM territories ORDER BY user_id")).all()


def run_state():
    with engine.connect() as c:
        return c.execute(text(
            "SELECT id, distance_km, territory_kind, round(awarded_area_sq_m::numeric, 3), "
            "round(observed_area_sq_m::numeric, 3) FROM runs ORDER BY id")).all()


def seed_old_style(client, make_user):
    a, b = make_user("Alice"), make_user("Bob")
    post(client, a, run_payload(square_loop_fixes(100.0)))
    post(client, b, run_payload(walk_fixes([(300, 0), (500, 0)])))
    step = 15.0 / (M_PER_DEG_LAT * cos(radians(LAT0)))
    coords = [[LAT0 + 0.003, LNG0 + i * step] for i in range(40)]
    post(client, b, {"distance_km": 0.6, "duration_seconds": 200, "avg_speed": 10.0,
                     "route_coordinates": coords})
    # Old rules: every territory was a 30 m buffer of the path.
    with engine.begin() as c:
        c.execute(text(
            "UPDATE territories SET geom = ST_Multi(ST_Buffer(geom::geography, 30)::geometry), "
            "area_sq_m = 1e9"))
    with engine.begin() as c:
        c.execute(text("UPDATE territories SET area_sq_m = ST_Area(geom::geography)"))


def test_reprocess_shrinks_territories_and_is_idempotent(client, make_user):
    import reprocess_territories as rp
    seed_old_style(client, make_user)
    old = {u: float(a) for u, a, _ in territory_state()}
    assert old[1] > 15_000 and old[2] > 20_000
    fixes_before = db_scalar("SELECT md5(string_agg(latitude::text || longitude::text || seq::text, ',' ORDER BY id)) FROM gps_fixes")
    runs_before = [(r[0], r[1]) for r in run_state()]

    assert rp.main(["--dry-run"]) == 0
    assert {u: float(a) for u, a, _ in territory_state()} == old  # dry run changed nothing

    assert rp.main([]) == 0
    new = {u: float(a) for u, a, _ in territory_state()}
    assert new[1] == pytest.approx(100 * 100, rel=0.05)           # the loop
    assert 200 * 6 * 0.9 < new[2] < 200 * 6 * 1.1 + 600 * 6 * 1.1  # two route strips
    assert db_scalar("SELECT territory_kind FROM runs WHERE id=1") == "loop"
    assert db_scalar("SELECT territory_kind FROM runs WHERE id=2") == "route"
    assert db_scalar("SELECT territory_kind FROM runs WHERE id=3") == "route"
    assert db_scalar("SELECT awarded_area_sq_m FROM runs WHERE id=1") == pytest.approx(new[1])
    types = geometry_types()
    assert types <= {"POLYGON", "MULTIPOLYGON"}

    # Distance and fixes are untouched.
    assert [(r[0], r[1]) for r in run_state()] == runs_before
    assert db_scalar("SELECT md5(string_agg(latitude::text || longitude::text || seq::text, ',' ORDER BY id)) FROM gps_fixes") == fixes_before

    # Second run is a no-op.
    t1, r1 = territory_state(), run_state()
    assert rp.main([]) == 0
    assert territory_state() == t1 and run_state() == r1


# --- migration -------------------------------------------------------------

NEW_COLUMNS = {
    "client_run_id", "started_at", "ended_at", "raw_distance_km", "client_distance_km",
    "uncertain_distance_m", "moving_time_s", "accepted_fix_count", "rejected_fix_count",
    "gap_count", "quality", "algorithm_version", "status", "processed_at",
    "processed_route_geom", "observed_corridor_geom", "awarded_geom",
    "observed_area_sq_m", "awarded_area_sq_m", "territory_kind",
}


def run_columns():
    with engine.connect() as c:
        return {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='runs'"))}


def test_setup_is_idempotent_and_upgrades_old_table():
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS gps_fixes, runs, territories, users CASCADE"))
        c.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR NOT NULL, "
                       "email VARCHAR NOT NULL UNIQUE, password_hash VARCHAR NOT NULL)"))
        c.execute(text(
            "CREATE TABLE territories (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE "
            "REFERENCES users(id), geom geometry(GEOMETRY,4326) NOT NULL, area_sq_m DOUBLE PRECISION NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"))
        c.execute(text(
            "CREATE TABLE runs (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), "
            "distance_km DOUBLE PRECISION NOT NULL, duration_seconds INTEGER NOT NULL, "
            "avg_speed DOUBLE PRECISION NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "route_geom geometry(LINESTRING,4326))"))
        c.execute(text("INSERT INTO users (name,email,password_hash) VALUES ('o','o@x.com','x')"))
        c.execute(text("INSERT INTO runs (user_id,distance_km,duration_seconds,avg_speed) VALUES (1,2.5,600,15)"))
        # A territory stored with the old, inflated Web-Mercator area.
        c.execute(text(
            "INSERT INTO territories (user_id, geom, area_sq_m) VALUES (1, "
            "ST_Buffer(ST_SetSRID(ST_MakePoint(75.9, 27.0),4326)::geography, 100)::geometry, 99999)"))
    assert NEW_COLUMNS.isdisjoint(run_columns())

    setup_database(engine)
    setup_database(engine)  # second run must not fail

    assert NEW_COLUMNS <= run_columns()
    assert db_scalar("SELECT distance_km FROM runs WHERE id=1") == 2.5
    assert db_scalar("SELECT count(*) FROM gps_fixes") == 0
    assert db_scalar("SELECT to_regclass('uq_runs_user_client_run_id') IS NOT NULL")
    true_area = db_scalar("SELECT ST_Area(geom::geography) FROM territories")
    assert db_scalar("SELECT area_sq_m FROM territories") == pytest.approx(true_area)

    # Old rows (NULL client_run_id) do not collide; a duplicate id does.
    with engine.begin() as c:
        c.execute(text("INSERT INTO runs (user_id,distance_km,duration_seconds,avg_speed) VALUES (1,1,1,1)"))
        c.execute(text("INSERT INTO runs (user_id,distance_km,duration_seconds,avg_speed,client_run_id) VALUES (1,1,1,1,'k')"))
    with pytest.raises(Exception):
        with engine.begin() as c:
            c.execute(text("INSERT INTO runs (user_id,distance_km,duration_seconds,avg_speed,client_run_id) VALUES (1,1,1,1,'k')"))
