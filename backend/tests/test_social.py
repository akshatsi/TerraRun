"""Following, feed, scoped territories and leaderboard against a real PostGIS."""
import pytest
from sqlalchemy import text

from app.database import engine
from tests.conftest import run_payload, square_loop_fixes


def signup(client, name):
    r = client.post("/auth/signup", json={
        "name": name, "email": f"{name.lower()}@example.com", "password": "secret123",
    })
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = client.get("/users/me", headers=h)  # sanity: token works
    assert uid.status_code == 200
    with engine.connect() as c:
        i = c.execute(text("SELECT id FROM users WHERE name=:n"), {"n": name}).scalar()
    return i, h


def add_run(client, h, x0=0.0, side=100.0):
    r = client.post("/runs", json=run_payload(square_loop_fixes(side_m=side, x0=x0)), headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def set_age(run_id, days):
    with engine.begin() as c:
        c.execute(text("UPDATE runs SET created_at = now() - make_interval(days => :d) WHERE id=:i"),
                  {"d": days, "i": run_id})


@pytest.fixture()
def trio(client):
    a = signup(client, "Alice")
    b = signup(client, "Bobby")
    c = signup(client, "Carol")
    return a, b, c


def test_follow_idempotent_and_counts(client, trio):
    (a, ah), (b, bh), (c, ch) = trio
    r = client.post(f"/users/{b}/follow", headers=ah)
    assert r.status_code == 200
    assert r.json()["is_following"] is True and r.json()["followers_count"] == 1
    assert client.post(f"/users/{b}/follow", headers=ah).json()["followers_count"] == 1
    client.post(f"/users/{a}/follow", headers=bh)
    card = client.get(f"/users/{b}", headers=ah).json()
    assert card["is_following"] is True and card["follows_you"] is True
    assert card["following_count"] == 1 and card["followers_count"] == 1
    assert card["recent_runs"] == []
    assert "email" not in card

    r = client.delete(f"/users/{b}/follow", headers=ah)
    assert r.status_code == 200 and r.json()["is_following"] is False
    assert r.json()["followers_count"] == 0
    assert client.delete(f"/users/{b}/follow", headers=ah).status_code == 200


def test_follow_errors(client, trio):
    (a, ah), _, _ = trio
    assert client.post(f"/users/{a}/follow", headers=ah).status_code == 400
    assert client.post("/users/9999/follow", headers=ah).status_code == 404
    assert client.delete("/users/9999/follow", headers=ah).status_code == 404
    assert client.get("/users/9999", headers=ah).status_code == 404
    assert client.post(f"/users/{a}/follow").status_code == 401


def test_following_followers_order(client, trio):
    (a, ah), (b, bh), (c, ch) = trio
    client.post(f"/users/{b}/follow", headers=ah)
    client.post(f"/users/{c}/follow", headers=ah)
    assert [u["id"] for u in client.get("/me/following", headers=ah).json()] == [c, b]
    client.post(f"/users/{c}/follow", headers=bh)
    followers = client.get("/me/followers", headers=ch).json()
    assert [u["id"] for u in followers] == [b, a]
    assert followers[0]["is_following"] is False and followers[0]["follows_you"] is True


def test_search(client, trio):
    (a, ah), (b, bh), (c, ch) = trio
    r = client.get("/users/search", params={"q": "ob"}, headers=ah)
    assert r.status_code == 200
    assert [u["name"] for u in r.json()] == ["Bobby"]
    assert "email" not in r.json()[0]
    # case-insensitive, email prefix, self excluded
    assert [u["id"] for u in client.get("/users/search", params={"q": "CAR"}, headers=ah).json()] == [c]
    assert [u["id"] for u in client.get("/users/search", params={"q": "bobby@"}, headers=ah).json()] == [b]
    assert client.get("/users/search", params={"q": "alice"}, headers=ah).json() == []
    assert client.get("/users/search", params={"q": "%%"}, headers=ah).json() == []
    assert client.get("/users/search", params={"q": "a"}, headers=ah).status_code == 422
    assert client.get("/users/search", headers=ah).status_code == 422
    assert client.get("/users/search", params={"q": "ob"}).status_code == 401


def test_user_card_stats_and_recent_runs(client, trio):
    (a, ah), (b, bh), _ = trio
    ids = [add_run(client, bh, x0=i * 300.0) for i in range(6)]
    card = client.get(f"/users/{b}", headers=ah).json()
    assert card["total_runs"] == 6 and card["total_distance_km"] > 0
    assert card["territory_area_sq_m"] > 0
    assert [r["run_id"] for r in card["recent_runs"]] == ids[::-1][:5]
    assert "user" not in card["recent_runs"][0]
    assert card["recent_runs"][0]["created_at"].endswith("Z")


def test_feed_and_paging(client, trio):
    (a, ah), (b, bh), (c, ch) = trio
    add_run(client, ah)
    rb = [add_run(client, bh, x0=i * 300.0) for i in range(3)]
    add_run(client, ch, x0=5000.0)
    assert client.get("/feed", headers=ah).json() == []
    client.post(f"/users/{b}/follow", headers=ah)
    items = client.get("/feed", headers=ah).json()
    assert [i["run_id"] for i in items] == rb[::-1]
    assert items[0]["user"] == {"id": b, "name": "Bobby"}
    assert items[0]["route_geojson"]["type"] == "MultiLineString"
    assert items[0]["territory_kind"] == "loop" and items[0]["awarded_area_sq_m"] > 0
    page = client.get("/feed", params={"limit": 2}, headers=ah).json()
    assert [i["run_id"] for i in page] == rb[::-1][:2]
    nxt = client.get("/feed", params={"limit": 2, "before_id": page[-1]["run_id"]}, headers=ah).json()
    assert [i["run_id"] for i in nxt] == [rb[0]]
    assert client.get("/feed", params={"limit": 0}, headers=ah).status_code == 422
    assert client.get("/feed", params={"limit": 51}, headers=ah).status_code == 422


def test_territory_scopes(client, trio):
    (a, ah), (b, bh), (c, ch) = trio
    add_run(client, ah)
    add_run(client, bh, x0=1000.0)
    add_run(client, ch, x0=2000.0)
    client.post(f"/users/{b}/follow", headers=ah)

    def users(params, headers=None):
        r = client.get("/territories", params=params, headers=headers)
        assert r.status_code == 200, r.text
        return sorted(t["user_id"] for t in r.json()["territories"])

    assert users({}) == [a, b, c]
    assert users({"scope": "all"}) == [a, b, c]
    assert users({"scope": "friends"}, ah) == [a, b]
    assert users({"scope": "mine"}, ah) == [a]
    assert users({"scope": "friends"}, ch) == [c]
    assert client.get("/territories", params={"scope": "friends"}).status_code == 401
    assert client.get("/territories", params={"scope": "mine"}).status_code == 401
    assert client.get("/territories", params={"scope": "bogus"}).status_code == 422


def test_leaderboard_scopes_and_week(client, trio):
    (a, ah), (b, bh), (c, ch) = trio
    add_run(client, ah)
    old = add_run(client, bh, x0=1000.0, side=200.0)
    add_run(client, bh, x0=1500.0)
    add_run(client, ch, x0=2000.0)
    set_age(old, 8)
    client.post(f"/users/{b}/follow", headers=ah)

    default = client.get("/leaderboard").json()
    assert {r["name"] for r in default} == {"Alice", "Bobby", "Carol"}
    assert all(r["is_me"] is False for r in default)
    assert set(default[0]) == {
        "name", "total_distance", "total_runs", "avg_speed", "territory_area", "user_id", "is_me",
    }
    dist = [r["total_distance"] for r in default]
    assert dist == sorted(dist, reverse=True)
    bobby_all = next(r for r in default if r["user_id"] == b)
    assert bobby_all["total_runs"] == 2

    mine = client.get("/leaderboard", headers=ah).json()
    assert [r["user_id"] for r in mine if r["is_me"]] == [a]

    friends = client.get("/leaderboard", params={"scope": "friends"}, headers=ah).json()
    assert {r["user_id"] for r in friends} == {a, b}

    week = client.get("/leaderboard", params={"period": "week"}, headers=ah).json()
    bobby_week = next(r for r in week if r["user_id"] == b)
    assert bobby_week["total_runs"] == 1
    assert bobby_week["total_distance"] < bobby_all["total_distance"]

    both = client.get("/leaderboard", params={"scope": "friends", "period": "week"}, headers=bh).json()
    assert {r["user_id"] for r in both} == {b}

    assert client.get("/leaderboard", params={"scope": "friends"}).status_code == 401
    assert client.get("/leaderboard", params={"period": "month"}).status_code == 422


def test_existing_routes_unchanged(client, trio):
    (a, ah), _, _ = trio
    assert client.get("/territories").json() == {"territories": []}
    assert client.get("/leaderboard").json() == []
    add_run(client, ah)
    t = client.get("/territories").json()["territories"]
    assert set(t[0]) == {"user_id", "user_name", "area_sq_m", "geojson"}
    assert client.get("/territories/me", headers=ah).status_code == 200
    assert client.get("/stats", headers=ah).status_code == 200
