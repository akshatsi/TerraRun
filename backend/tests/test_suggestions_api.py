"""Road cache and GET /suggestions against a real PostGIS and a synthetic street grid."""
from datetime import datetime, timedelta, timezone
from math import cos, radians

import pytest
from sqlalchemy import text

from app.database import SessionLocal, engine
from app.routes.suggestion_routes import _popularity, get_road_fetcher
from app.routing.roads import RoadDataUnavailable, get_roads
from tests.conftest import LAT0, LNG0, M_PER_DEG_LAT

M_PER_DEG_LNG = M_PER_DEG_LAT * cos(radians(LAT0))
CENTER = (LAT0, LNG0)


def ll(x, y):
    """(lat, lng) of a point x metres east and y metres north of the origin."""
    return LAT0 + y / M_PER_DEG_LAT, LNG0 + x / M_PER_DEG_LNG


def element(osm_id, pts_m, **tags):
    tags.setdefault("highway", "residential")
    return {
        "type": "way", "id": osm_id, "tags": tags,
        "geometry": [{"lat": ll(x, y)[0], "lon": ll(x, y)[1]} for x, y in pts_m],
    }


def grid_elements(half=600, step=100):
    """Streets every 100 m over a 1.2 km square, plus ways that must be ignored."""
    els, oid = [], 1000
    for k in range(-half, half + 1, step):
        els.append(element(oid, [(-half, k), (half, k)])); oid += 1       # east-west
        els.append(element(oid, [(k, -half), (k, half)])); oid += 1       # north-south
    els.append(element(1, [(0, 0), (50, 50)], highway="footway"))
    els.append(element(2, [(0, 0), (-50, 50)], highway="service", service="driveway"))
    els.append(element(3, [(0, 0), (50, -50)], highway="residential", access="private"))
    return els


class Fetcher:
    def __init__(self, elements=None, fail=False):
        self.elements = grid_elements() if elements is None else elements
        self.fail = fail
        self.calls = []

    def __call__(self, bbox):
        self.calls.append(bbox)
        if self.fail:
            raise RuntimeError("overpass down")
        return self.elements


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def fetcher(client):
    from app.main import app
    f = Fetcher()
    app.dependency_overrides[get_road_fetcher] = lambda: f
    yield f
    app.dependency_overrides.pop(get_road_fetcher, None)


# --- cache -----------------------------------------------------------------

def test_first_call_fetches_second_uses_cache(db):
    f = Fetcher()
    first = get_roads(db, CENTER, 400, fetcher=f)
    assert len(f.calls) == 1
    ids = {r.osm_id for r in first}
    assert ids and not ids & {1, 2, 3}
    second = get_roads(db, CENTER, 400, fetcher=f)
    assert len(f.calls) == 1
    assert {r.osm_id for r in second} == ids
    # points come back as (lat, lng) in order
    road = next(r for r in second if r.osm_id == 1012)
    assert road.points[0][0] == pytest.approx(LAT0, abs=1e-6)
    assert road.points[0][1] < road.points[-1][1]


def test_radius_limits_roads(db):
    f = Fetcher()
    near = get_roads(db, CENTER, 150, fetcher=f)
    far = get_roads(db, CENTER, 700, fetcher=f)
    assert 0 < len(near) < len(far)


def test_stale_tile_is_refetched(db):
    f = Fetcher()
    get_roads(db, CENTER, 300, fetcher=f)
    get_roads(db, CENTER, 300, fetcher=f, now=datetime.now(timezone.utc) + timedelta(days=29))
    assert len(f.calls) == 1
    get_roads(db, CENTER, 300, fetcher=f, now=datetime.now(timezone.utc) + timedelta(days=31))
    assert len(f.calls) == 2


def test_only_missing_tiles_are_fetched(db):
    f = Fetcher()
    get_roads(db, CENTER, 300, fetcher=f)
    n = len(f.calls)
    get_roads(db, CENTER, 300, fetcher=f)
    assert len(f.calls) == n
    # A circle reaching a neighbouring tile fetches just that area again.
    get_roads(db, (LAT0 + 0.0095, LNG0), 300, fetcher=f)
    assert len(f.calls) == n + 1
    south, _, north, _ = f.calls[-1]
    assert north - south == pytest.approx(0.01, abs=1e-9)


def test_fetch_failure_with_cache_uses_cache(db):
    ok = Fetcher()
    cached = get_roads(db, CENTER, 300, fetcher=ok)
    bad = Fetcher(fail=True)
    later = datetime.now(timezone.utc) + timedelta(days=40)
    again = get_roads(db, CENTER, 300, fetcher=bad, now=later)
    assert len(bad.calls) == 1
    assert {r.osm_id for r in again} == {r.osm_id for r in cached}


def test_fetch_failure_without_cache_raises(db):
    with pytest.raises(RoadDataUnavailable):
        get_roads(db, CENTER, 300, fetcher=Fetcher(fail=True))
    assert db.execute(text("SELECT count(*) FROM road_tiles")).scalar() == 0


def test_refetch_replaces_removed_roads(db):
    get_roads(db, CENTER, 300, fetcher=Fetcher())
    only_one = Fetcher(elements=[element(5000, [(-100, 0), (100, 0)])])
    later = datetime.now(timezone.utc) + timedelta(days=31)
    roads = get_roads(db, CENTER, 300, fetcher=only_one, now=later)
    assert [r.osm_id for r in roads] == [5000]


# --- endpoint --------------------------------------------------------------

def user_id(name):
    with engine.connect() as c:
        return c.execute(text("SELECT id FROM users WHERE name=:n"), {"n": name}).scalar()


def set_territory(uid, x0, y0, x1, y1):
    (la0, ln0), (la1, ln1) = ll(x0, y0), ll(x1, y1)
    wkt = (f"POLYGON(({ln0} {la0},{ln1} {la0},{ln1} {la1},{ln0} {la1},{ln0} {la0}))")
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO territories (user_id, geom, area_sq_m) VALUES "
            "(:u, ST_GeomFromText(:w, 4326), ST_Area(ST_GeomFromText(:w, 4326)::geography))"
        ), {"u": uid, "w": wkt})


def add_runs(uid, n, km, seconds):
    with engine.begin() as c:
        for _ in range(n):
            c.execute(text(
                "INSERT INTO runs (user_id, distance_km, duration_seconds, avg_speed) "
                "VALUES (:u, :d, :s, 10)"), {"u": uid, "d": km, "s": seconds})


def ask(client, headers, **params):
    return client.get("/suggestions", params={"lat": LAT0, "lng": LNG0, **params}, headers=headers)


def test_requires_token(client, fetcher):
    assert client.get("/suggestions", params={"lat": LAT0, "lng": LNG0}).status_code == 401


@pytest.mark.parametrize("params", [
    {"lat": 91}, {"lng": 181}, {"lat": "x"},
    {"distance_km": 0.2}, {"distance_km": 16}, {"minutes": 2}, {"minutes": 181},
    {"distance_km": 2, "minutes": 20},
])
def test_validation_errors(client, fetcher, auth, params):
    params = {"lat": LAT0, "lng": LNG0, **params}
    assert client.get("/suggestions", params=params, headers=auth).status_code == 422


def test_defaults_without_history(client, fetcher, auth):
    r = ask(client, auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pace_s_per_km"] == 390 and body["target_distance_km"] == 2.0


def test_suggestions_shape(client, fetcher, auth):
    body = ask(client, auth, distance_km=2).json()
    assert body["suggestions"], body
    assert len(body["suggestions"]) <= 3
    for s in body["suggestions"]:
        assert 1.5 <= s["distance_km"] <= 2.5
        assert s["estimated_minutes"] == pytest.approx(s["distance_km"] * 390 / 60, abs=1)
        line = s["route_geojson"]
        assert line["type"] == "LineString"
        lng, lat = line["coordinates"][0]
        assert abs(lng - LNG0) < 0.05 and abs(lat - LAT0) < 0.05  # [lng, lat] order
        assert line["coordinates"][0] == line["coordinates"][-1]
        assert s["area_geojson"]["type"] in ("Polygon", "MultiPolygon")
        assert s["gain_sq_m"] == pytest.approx(s["new_area_sq_m"] + s["stolen_area_sq_m"], abs=1)
        assert s["label"] and s["reason"]
        assert s["stolen_from"] == [] and s["stolen_area_sq_m"] == 0  # nobody followed


def test_only_followed_friends_are_stolen_from(client, fetcher, make_user):
    alice, bob, carol = make_user("Alice"), make_user("Bobby"), make_user("Carol")
    bob_id, carol_id = user_id("Bobby"), user_id("Carol")
    set_territory(bob_id, 0, 0, 400, 400)
    set_territory(carol_id, -400, 0, 0, 400)

    # Not following anyone: other people's land is just empty land.
    for s in ask(client, alice, distance_km=2).json()["suggestions"]:
        assert s["stolen_area_sq_m"] == 0 and s["stolen_from"] == []

    assert client.post(f"/users/{bob_id}/follow", headers=alice).status_code == 200
    body = ask(client, alice, distance_km=2).json()
    stolen = [s for s in body["suggestions"] if s["stolen_area_sq_m"] > 0]
    assert stolen, body
    for s in body["suggestions"]:
        assert {f["user_id"] for f in s["stolen_from"]} <= {bob_id}
        assert carol_id not in {f["user_id"] for f in s["stolen_from"]}
        assert sum(f["area_sq_m"] for f in s["stolen_from"]) == pytest.approx(
            s["stolen_area_sq_m"], abs=1)
    assert stolen[0]["stolen_from"][0]["name"] == "Bobby"


def test_pace_and_usual_distance_from_history(client, fetcher, auth):
    add_runs(user_id("Alice"), 3, 3.0, 1200)  # 400 s/km, 3 km
    body = ask(client, auth).json()
    assert body["pace_s_per_km"] == 400 and body["target_distance_km"] == 3.0
    body = ask(client, auth, minutes=20).json()  # 20 min at 400 s/km = 3 km
    assert body["target_distance_km"] == 3.0
    body = ask(client, auth, distance_km=1.5).json()
    assert body["target_distance_km"] == 1.5
    for s in body["suggestions"]:
        assert s["estimated_minutes"] == pytest.approx(s["distance_km"] * 400 / 60, abs=1)


def test_usual_distance_is_clamped(client, fetcher, auth):
    add_runs(user_id("Alice"), 3, 0.2, 100)
    assert ask(client, auth).json()["target_distance_km"] == 0.8
    add_runs(user_id("Alice"), 6, 20.0, 6000)
    assert ask(client, auth).json()["target_distance_km"] == 8.0


def test_no_roads_gives_message(client, auth):
    from app.main import app
    app.dependency_overrides[get_road_fetcher] = lambda: Fetcher(elements=[])
    try:
        body = ask(client, auth).json()
    finally:
        app.dependency_overrides.pop(get_road_fetcher, None)
    assert body["suggestions"] == [] and body["message"]


def test_503_when_roads_unavailable(client, auth):
    from app.main import app
    app.dependency_overrides[get_road_fetcher] = lambda: Fetcher(fail=True)
    try:
        r = ask(client, auth)
    finally:
        app.dependency_overrides.pop(get_road_fetcher, None)
    assert r.status_code == 503 and r.json()["detail"]


# --- popularity ------------------------------------------------------------

def test_popularity_counts_only_friends_runs(client, db, make_user):
    make_user("Alice"); make_user("Bobby"); make_user("Carol")
    bob_id, carol_id = user_id("Bobby"), user_id("Carol")
    get_roads(db, CENTER, 500, fetcher=Fetcher())
    (la, ln0), (_, ln1) = ll(-300, 0), ll(300, 0)
    wkt = f"MULTILINESTRING(({ln0} {la},{ln1} {la}))"
    with engine.begin() as c:
        for uid, n in ((bob_id, 2), (carol_id, 5)):
            for _ in range(n):
                c.execute(text(
                    "INSERT INTO runs (user_id, distance_km, duration_seconds, avg_speed, "
                    "processed_route_geom) VALUES (:u, 1, 400, 9, ST_GeomFromText(:w, 4326))"
                ), {"u": uid, "w": wkt})
    with engine.connect() as c:
        road_y0 = c.execute(text(
            "SELECT osm_id FROM road_ways WHERE ST_DWithin(geom::geography, "
            "ST_SetSRID(ST_MakePoint(:x, :y), 4326)::geography, 5) "
            "AND ST_Y(ST_StartPoint(geom)) = ST_Y(ST_EndPoint(geom)) LIMIT 1"
        ), {"x": ln0 + 0.0001, "y": la}).scalar()
        all_ids = [r[0] for r in c.execute(text("SELECT osm_id FROM road_ways"))]
    bbox = (la - 0.01, ln0 - 0.01, la + 0.01, ln1 + 0.01)
    pop = _popularity(db, [bob_id], all_ids, bbox)
    assert pop.get(road_y0) == 2
    assert _popularity(db, [], all_ids, bbox) == {}
    assert _popularity(db, [bob_id, carol_id], all_ids, bbox)[road_y0] == 7
