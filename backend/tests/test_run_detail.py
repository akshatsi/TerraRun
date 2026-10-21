"""GET /runs/{id}, PATCH /users/me and GET /users/me/card against PostGIS."""
import pytest
from sqlalchemy import text

from app.database import engine
from tests.conftest import LAT0, M_PER_DEG_LAT, make_fixes, run_payload, square_loop_fixes


def post(client, h, fixes, **kw):
    r = client.post("/runs", json=run_payload(fixes, **kw), headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_steady_run_detail(client, auth):
    rid = post(client, auth, make_fixes(n=834, speed=3.0))
    r = client.get(f"/runs/{rid}", headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["run_id"] == rid and d["is_mine"] is True and d["user"]["name"] == "Alice"
    assert [s["km"] for s in d["splits"]] == [1, 2, 3]
    assert d["splits"][0]["duration_s"] == pytest.approx(333.3, abs=1)
    assert d["splits"][1]["pace_s_per_km"] == pytest.approx(333, abs=1)
    assert d["splits"][2]["distance_m"] == pytest.approx(500, abs=5)
    assert d["distance_km"] == pytest.approx(2.5, rel=0.03)
    assert d["avg_speed_kmh"] == pytest.approx(10.8, rel=0.05)
    assert d["avg_pace_s_per_km"] == pytest.approx(333, rel=0.05)
    assert d["max_speed_kmh"] == 10.8
    assert d["elevation_gain_m"] == 0.0
    assert d["route_geojson"]["type"] == "MultiLineString"
    assert set(d["territory"]) == {"kind", "awarded_area_sq_m", "reason"}
    assert "awarded_geojson" in d and "moving_time_s" in d and "quality" in d


def test_gap_run_splits_skip_gap(client, auth):
    dlat = 3000.0 / M_PER_DEG_LAT
    a = make_fixes(n=200, speed=3.0)
    b = make_fixes(lat=LAT0 + dlat, n=200, speed=3.0, t_start=1000)
    d = client.get(f"/runs/{post(client, auth, a + b)}", headers=auth).json()
    total = sum(s["distance_m"] for s in d["splits"])
    assert total == pytest.approx(2 * 597, rel=0.03)
    assert sum(s["duration_s"] for s in d["splits"]) == pytest.approx(398, abs=5)
    assert d["splits"][0]["duration_s"] == pytest.approx(333, abs=3)


def test_elevation_gain_with_noise(client, auth):
    fixes = make_fixes(n=834, speed=3.0)
    for i, f in enumerate(fixes):
        f["altitude_m"] = 400 + i * 0.03 + (0.4 if i % 2 else -0.4)
    d = client.get(f"/runs/{post(client, auth, fixes)}", headers=auth).json()
    assert d["elevation_gain_m"] == pytest.approx(25, abs=2.5)
    assert d["splits"][0]["elevation_change_m"] == pytest.approx(10, abs=1.5)


def test_no_altitude_and_no_speed(client, auth):
    fixes = make_fixes(n=100, speed=3.0)
    for f in fixes:
        f["altitude_m"] = None
        f["speed_mps"] = None
    d = client.get(f"/runs/{post(client, auth, fixes)}", headers=auth).json()
    assert d["elevation_gain_m"] is None
    assert d["max_speed_kmh"] == pytest.approx(10.8, abs=0.5)


def test_legacy_run_without_fixes(client, auth):
    r = client.post("/runs", json={"distance_km": 3.2, "duration_seconds": 1000, "avg_speed": 11.5},
                    headers=auth)
    d = client.get(f"/runs/{r.json()['id']}", headers=auth).json()
    assert d["splits"] == []
    assert d["elevation_gain_m"] is None and d["max_speed_kmh"] is None
    assert d["distance_km"] == 3.2
    assert d["avg_pace_s_per_km"] == round(1000 / 3.2)
    assert d["avg_speed_kmh"] == pytest.approx(3.2 / (1000 / 3600), abs=0.01)


def test_zero_distance_run_has_null_pace(client, auth):
    r = client.post("/runs", json={"distance_km": 0, "duration_seconds": 60, "avg_speed": 0},
                    headers=auth)
    d = client.get(f"/runs/{r.json()['id']}", headers=auth).json()
    assert d["avg_pace_s_per_km"] is None and d["avg_speed_kmh"] == 0


def test_404_auth_and_other_users_run(client, make_user, auth):
    assert client.get("/runs/9999", headers=auth).status_code == 404
    rid = post(client, auth, square_loop_fixes())
    assert client.get(f"/runs/{rid}").status_code == 401
    other = make_user("Bobby")
    d = client.get(f"/runs/{rid}", headers=other).json()
    assert d["is_mine"] is False and d["user"]["name"] == "Alice"
    assert d["territory"]["kind"] == "loop" and d["awarded_geojson"] is not None


def test_patch_and_card(client, auth, make_user):
    me = client.get("/users/me/card", headers=auth)
    assert me.status_code == 200 and me.json()["bio"] is None and me.json()["name"] == "Alice"
    uid = me.json()["id"]

    r = client.patch("/users/me", json={"name": "  Alicia  ", "bio": "  Trail runner  "}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Alicia" and r.json()["bio"] == "Trail runner"
    assert client.get("/users/me", headers=auth).json()["user_name"] == "Alicia"

    # Partial update leaves the other field alone.
    assert client.patch("/users/me", json={"name": "Alice"}, headers=auth).json()["bio"] == "Trail runner"
    # Empty bio clears it.
    assert client.patch("/users/me", json={"bio": "   "}, headers=auth).json()["bio"] is None
    assert client.get("/users/me/card", headers=auth).json()["bio"] is None

    for bad in ({"name": "A"}, {"name": " "}, {"name": "x" * 41}, {"bio": "y" * 161}, {"name": None}):
        assert client.patch("/users/me", json=bad, headers=auth).status_code == 422, bad
    assert client.patch("/users/me", json={"bio": "y" * 160}, headers=auth).status_code == 200
    assert client.patch("/users/me", json={"name": "Al"}).status_code == 401

    # Bio shows in search, following and the user detail.
    client.patch("/users/me", json={"bio": "hello there"}, headers=auth)
    bob = make_user("Bobby")
    assert client.get("/users/search", params={"q": "Al"}, headers=bob).json()[0]["bio"] == "hello there"
    client.post(f"/users/{uid}/follow", headers=bob)
    assert client.get("/me/following", headers=bob).json()[0]["bio"] == "hello there"
    assert client.get(f"/users/{uid}", headers=bob).json()["bio"] == "hello there"


def test_setup_adds_bio_column_to_old_users_table():
    from setup_postgis import setup_database
    with engine.begin() as c:
        c.execute(text("ALTER TABLE users DROP COLUMN bio"))
    setup_database(engine)
    setup_database(engine)
    with engine.connect() as c:
        assert c.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='users' AND column_name='bio'")).scalar() == 1
