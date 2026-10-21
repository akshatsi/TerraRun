"""Splits, elevation gain and top speed maths. No database."""
import pytest

from app.gps.geodesy import offset_point
from app.gps.splits import TrackPoint, compute_splits, elevation_gain_m, max_speed_kmh


def track(n, speed=3.0, t0=0.0, segment=0, east0=0.0, alt=lambda i: 400.0, reported=True):
    out = []
    for i in range(n):
        lat, lng = offset_point(27.0, 75.9, east0 + speed * i, 0.0)
        out.append(TrackPoint(lat, lng, t0 + i, segment, alt(i), speed if reported else None))
    return out


def test_steady_run_splits():
    sp = compute_splits(track(834))        # 2499 m
    assert [s.km for s in sp] == [1, 2, 3]
    assert sp[0].duration_s == pytest.approx(333.3, abs=0.5)
    assert sp[1].duration_s == pytest.approx(333.3, abs=0.5)
    assert sp[0].pace_s_per_km == 333 and sp[1].pace_s_per_km == 333
    assert sp[2].distance_m == pytest.approx(499, abs=2)
    assert sp[2].duration_s == pytest.approx(166.3, abs=1)
    assert sum(s.distance_m for s in sp) == pytest.approx(2499, abs=1)


def test_short_run_has_one_partial_split():
    sp = compute_splits(track(100))
    assert len(sp) == 1 and sp[0].distance_m == pytest.approx(297, abs=1)


def test_too_few_points():
    assert compute_splits([]) == []
    assert compute_splits(track(1)) == []


def test_gap_time_and_distance_do_not_count():
    a = track(200)                                        # 597 m, t 0..199
    b = track(200, t0=1000.0, segment=1, east0=5000.0)    # far away, 800 s later
    sp = compute_splits(a + b)
    assert sum(s.distance_m for s in sp) == pytest.approx(2 * 597, abs=2)
    assert sp[0].km == 1 and sp[0].distance_m == 1000
    assert sp[0].duration_s == pytest.approx(333.3, abs=0.5)    # not 1000+ s
    assert sp[-1].duration_s == pytest.approx(sum(s.duration_s for s in sp[-1:]))
    assert sum(s.duration_s for s in sp) == pytest.approx(398, abs=1)


def test_elevation_ignores_noise_and_counts_climb():
    flat = [TrackPoint(27.0, 75.9 + i * 1e-5, i, 0, 400.0 + (0.4 if i % 2 else -0.4)) for i in range(100)]
    assert elevation_gain_m(flat) == 0.0
    climb = track(834, alt=lambda i: 400 + i * 0.03 + (0.4 if i % 2 else -0.4))
    assert elevation_gain_m(climb) == pytest.approx(25, abs=2)
    sp = compute_splits(climb)
    assert sp[0].elevation_change_m == pytest.approx(10, abs=1)


def test_no_altitudes():
    pts = track(50, alt=lambda i: None)
    assert elevation_gain_m(pts) is None
    assert all(s.elevation_change_m is None for s in compute_splits(track(400, alt=lambda i: None)))


def test_max_speed_reported_and_derived():
    pts = track(30, speed=3.0)
    assert max_speed_kmh(pts) == 10.8
    derived = track(30, speed=4.0, reported=False)
    assert max_speed_kmh(derived) == pytest.approx(14.4, abs=0.2)
    assert max_speed_kmh(track(3, reported=False)) is None
