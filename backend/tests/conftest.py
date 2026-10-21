"""Test setup. Needs a real PostGIS database; tables are truncated per test.

    DATABASE_URL=postgresql://test:test@localhost:55432/test APP_ENV=development \
        .venv/bin/python -m pytest tests -q
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from math import cos, radians
from pathlib import Path

import pytest

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_url = os.environ.get("DATABASE_URL", "")
# The database tests truncate every table, so they only run against a database
# whose name contains "test". The engine tests need no database and always run.
DB_OK = "test" in _url.rsplit("/", 1)[-1]
DB_FREE_MODULES = {"test_gps_engine.py", "test_territory_shape.py", "test_splits.py"}


def pytest_collection_modifyitems(config, items):
    if DB_OK:
        return
    skip = pytest.mark.skip(
        reason="needs DATABASE_URL pointing at a database named *test*"
    )
    for item in items:
        if item.path.name not in DB_FREE_MODULES:
            item.add_marker(skip)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from setup_postgis import setup_database  # noqa: E402

T0 = datetime(2026, 10, 17, 6, 0, 0, tzinfo=timezone.utc)
LAT0, LNG0 = 27.0, 75.9
M_PER_DEG_LAT = 111_320.0


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def make_fixes(lat=LAT0, lng=LNG0, n=60, speed=3.0, t_start=0.0, accuracy=5.0, heading="east"):
    """n fixes, 1 per second, moving east (or north) at `speed` m/s."""
    out = []
    for i in range(n):
        d = speed * i
        if heading == "east":
            la, ln = lat, lng + d / (M_PER_DEG_LAT * cos(radians(lat)))
        else:
            la, ln = lat + d / M_PER_DEG_LAT, lng
        out.append({
            "lat": la, "lng": ln, "t": iso(T0 + timedelta(seconds=t_start + i)),
            "accuracy_m": accuracy, "speed_mps": speed, "heading_deg": 90.0, "altitude_m": 400.0,
        })
    return out


def walk_fixes(corners_m, speed=3.0, t_start=0.0, accuracy=5.0):
    """Fixes 1 per second along a path of (east_m, north_m) corners, in metres
    from (LAT0, LNG0). The walk starts at the first corner."""
    pts = [corners_m[0]]
    for (x0, y0), (x1, y1) in zip(corners_m, corners_m[1:]):
        n = max(1, round(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / speed))
        for k in range(1, n + 1):
            pts.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    out = []
    for i, (x, y) in enumerate(pts):
        out.append({
            "lat": LAT0 + y / M_PER_DEG_LAT,
            "lng": LNG0 + x / (M_PER_DEG_LAT * cos(radians(LAT0))),
            "t": iso(T0 + timedelta(seconds=t_start + i)),
            "accuracy_m": accuracy, "speed_mps": speed, "heading_deg": 90.0, "altitude_m": 400.0,
        })
    return out


def square_loop_fixes(side_m=100.0, x0=0.0, y0=0.0, **kw):
    """A closed square walk that starts and ends at the same corner."""
    c = [(x0, y0), (x0 + side_m, y0), (x0 + side_m, y0 + side_m), (x0, y0 + side_m), (x0, y0)]
    return walk_fixes(c, **kw)


def run_payload(fixes, client_run_id=None, **extra):
    body = {
        "client_run_id": client_run_id or os.urandom(16).hex(),
        "started_at": fixes[0]["t"] if fixes else iso(T0),
        "ended_at": fixes[-1]["t"] if fixes else iso(T0),
        "duration_seconds": len(fixes),
        "client_distance_km": 0.1,
        "fixes": fixes,
    }
    body.update(extra)
    return body


def _needs_db(request) -> bool:
    return DB_OK and request.node.path.name not in DB_FREE_MODULES


@pytest.fixture(scope="session")
def _schema():
    setup_database(engine)
    yield


@pytest.fixture(autouse=True)
def _clean(request):
    if not _needs_db(request):
        yield
        return
    request.getfixturevalue("_schema")
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE follows, gps_fixes, runs, territories, users RESTART IDENTITY CASCADE"
        ))
    yield


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def make_user(client):
    counter = {"n": 0}

    def _make(name=None):
        counter["n"] += 1
        name = name or f"Runner{counter['n']}"
        r = client.post("/auth/signup", json={
            "name": name, "email": f"{name.lower()}@example.com", "password": "secret123",
        })
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make


@pytest.fixture()
def auth(make_user):
    return make_user("Alice")
