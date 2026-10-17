"""Geometry engine: true-metre areas, loops, routes, awards, rivals."""
import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.territory import build_multilinestring, claim_territory
from tests.conftest import LAT0, LNG0, M_PER_DEG_LAT, square_loop_fixes, walk_fixes
from math import cos, radians

STRIP_WIDTH_M = 6.0  # 3 m each side


def lng_off(m, lat=LAT0):
    return m / (M_PER_DEG_LAT * cos(radians(lat)))


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def add_user(db, uid):
    db.execute(text(
        "INSERT INTO users (id, name, email, password_hash) VALUES (:i, :n, :e, 'x')"
    ), {"i": uid, "n": f"u{uid}", "e": f"u{uid}@x.com"})


def line_east(length_m, lat=LAT0, lng=LNG0):
    """Dense points (every ~5 m) along a straight east line."""
    n = max(2, round(length_m / 5) + 1)
    return [(lat, lng + lng_off(length_m * k / (n - 1), lat)) for k in range(n)]


def loop_segment(side_m=100.0, x0=0.0, y0=0.0):
    return [(f["lat"], f["lng"]) for f in square_loop_fixes(side_m, x0, y0)]


def geom_types(db, uid):
    return db.execute(text(
        "SELECT GeometryType(geom) FROM territories WHERE user_id=:u"), {"u": uid}).scalar()


def test_route_area_is_a_flat_ended_strip(db):
    add_user(db, 1)
    r = claim_territory(db, 1, [line_east(100)], "good", 100.0)
    assert r["kind"] == "route"
    assert r["observed_area_sq_m"] == pytest.approx(100 * STRIP_WIDTH_M, rel=0.05)


def test_area_not_inflated_at_latitude(db):
    # The old Web-Mercator method would give ~ +26% at 27 deg N.
    add_user(db, 1)
    r = claim_territory(db, 1, [line_east(200)], "good", 200.0)
    assert r["observed_area_sq_m"] < 200 * STRIP_WIDTH_M * 1.06


def test_segments_not_joined_across_gap(db):
    add_user(db, 1)
    a = line_east(100)
    b = line_east(100, lat=LAT0 + 0.01)  # about 1.1 km north
    r = claim_territory(db, 1, [a, b], "good", 200.0, uncertain_distance_m=1100.0)
    assert r["kind"] == "route"
    assert r["observed_area_sq_m"] == pytest.approx(2 * 100 * STRIP_WIDTH_M, rel=0.06)


def test_short_segments_skipped():
    assert build_multilinestring([[(LAT0, LNG0)]]) is None


def test_loop_awards_only_the_enclosed_area(db):
    add_user(db, 1)
    r = claim_territory(db, 1, [loop_segment(100)], "good", 400.0)
    assert r["kind"] == "loop"
    assert r["reason"]
    assert r["awarded_area_sq_m"] == pytest.approx(100 * 100, rel=0.05)
    assert r["total_area_sq_m"] == pytest.approx(r["awarded_area_sq_m"])


def test_award_rules(db):
    add_user(db, 1)
    seg = [line_east(100)]
    poor = claim_territory(db, 1, seg, "poor", 100.0)
    assert poor["kind"] == "none"
    assert poor["awarded_area_sq_m"] == 0 and poor["total_area_sq_m"] == 0
    assert poor["observed_area_sq_m"] > 0
    short = claim_territory(db, 1, seg, "good", 49.0)
    assert short["kind"] == "none"
    assert short["awarded_area_sq_m"] == 0 and short["total_area_sq_m"] == 0
    ok = claim_territory(db, 1, seg, "good", 100.0)
    assert ok["kind"] == "route"
    assert ok["awarded_area_sq_m"] == pytest.approx(ok["observed_area_sq_m"])
    assert ok["total_area_sq_m"] == pytest.approx(ok["awarded_area_sq_m"])
    unv = claim_territory(db, 1, seg, "unverified", 100.0)
    assert unv["awarded_area_sq_m"] > 0
    assert claim_territory(db, 1, [], "good", 100.0)["kind"] == "none"


def test_rival_subtraction_and_removal(db):
    add_user(db, 1)
    add_user(db, 2)
    before = claim_territory(db, 1, [line_east(200)], "good", 200.0)["total_area_sq_m"]
    # Rival's strip crosses the east half and runs beyond.
    mid = LNG0 + lng_off(100)
    r = claim_territory(db, 2, [line_east(300, lng=mid)], "good", 300.0)
    a_area = db.execute(text("SELECT area_sq_m FROM territories WHERE user_id=1")).scalar()
    assert before * 0.4 < a_area < before * 0.6
    stored = db.execute(text(
        "SELECT area_sq_m, ST_Area(geom::geography) FROM territories WHERE user_id=1"
    )).first()
    assert stored[0] == pytest.approx(stored[1])
    # Rival now covers the rest (the same road, starting 10 m earlier): row removed.
    claim_territory(db, 2, [line_east(400, lng=LNG0 - lng_off(10))], "good", 400.0)
    assert db.execute(text("SELECT count(*) FROM territories WHERE user_id=1")).scalar() == 0
    assert r["total_area_sq_m"] > 0


def test_loop_over_rival_strip_leaves_only_polygons(db):
    add_user(db, 1)
    add_user(db, 2)
    # User 1 owns a strip that runs through the middle of where user 2 will loop.
    strip = [(LAT0 + 50 / M_PER_DEG_LAT, LNG0 - lng_off(50) + lng_off(k * 5)) for k in range(41)]
    claim_territory(db, 1, [strip], "good", 200.0)
    full = db.execute(text("SELECT area_sq_m FROM territories WHERE user_id=1")).scalar()
    claim_territory(db, 2, [loop_segment(100)], "good", 400.0)
    left = db.execute(text("SELECT area_sq_m FROM territories WHERE user_id=1")).scalar()
    # About 100 m of the 200 m strip lies inside the square.
    assert left == pytest.approx(full - 100 * STRIP_WIDTH_M, rel=0.1)
    assert geom_types(db, 1) in ("POLYGON", "MULTIPOLYGON")
    assert geom_types(db, 2) in ("POLYGON", "MULTIPOLYGON")
