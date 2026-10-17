"""Territory shape rules v2 (app/gps/territory_shape.py). No database needed."""
import math

import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from app.gps import process_track
from app.gps import synthetic as syn
from app.gps.geodesy import offset_point
from app.gps.territory_shape import ShapeConfig, TerritoryShape, build_territory_shape

LAT0, LNG0 = 26.9342, 75.9241


def ll(x, y):
    """Local metres (east, north) from the origin to (lat, lng)."""
    return offset_point(LAT0, LNG0, x, y)


def densify(corners, step=5.0):
    """Points every `step` metres along a polyline given in local metres."""
    out = [corners[0]]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:]):
        n = max(1, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / step)))
        out += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(1, n + 1)]
    return out


def seg(corners, step=5.0):
    return [ll(x, y) for x, y in densify(corners, step)]


def at(shape, x, y):
    lat, lng = ll(x, y)
    return shape.geometry.contains(Point(lng, lat))


def check(shape):
    """Every non-empty shape is a valid Polygon/MultiPolygon in plausible lon/lat."""
    assert isinstance(shape, TerritoryShape)
    if shape.kind == "none":
        assert shape.geometry is None and shape.area_sq_m == 0.0
        return
    g = shape.geometry
    assert isinstance(g, (Polygon, MultiPolygon))
    assert g.is_valid and not g.is_empty
    for p in getattr(g, "geoms", [g]):
        assert not p.is_empty and p.area > 0
    minx, miny, maxx, maxy = g.bounds
    assert 75.9 < minx <= maxx < 75.95 and 26.92 < miny <= maxy < 26.95
    assert shape.area_sq_m > 0 and shape.reason


SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]


def test_square_loop():
    s = build_territory_shape([seg([(0, 0), (100, 0), (100, 100), (0, 100), (0, 4)])])
    check(s)
    assert s.kind == "loop"
    assert s.closure_distance_m == pytest.approx(4, abs=0.01)
    assert s.area_sq_m == pytest.approx(10_000, rel=0.02)
    assert "Loop closed 4 m" in s.reason


def test_square_ending_30m_away_is_route():
    s = build_territory_shape([seg([(0, 0), (100, 0), (100, 100), (0, 100), (0, 30)])])
    check(s)
    assert s.kind == "route"
    assert s.closure_distance_m == pytest.approx(30, abs=0.01)
    # 370 m of path, 6 m wide, flat ends; round joins lose ~1.9 m2 per corner.
    assert s.area_sq_m == pytest.approx(370 * 6, rel=0.03)
    assert not at(s, 50, 50)  # no enclosed area
    assert not at(s, 0, 30 - 1)  # flat end: nothing beyond the last fix
    assert "ended 30 m from start" in s.reason


def test_straight_140m():
    s = build_territory_shape([seg([(0, 0), (140, 0)])])
    check(s)
    assert s.kind == "route"
    assert s.area_sq_m == pytest.approx(840, rel=0.01)  # old 30 m round-cap rule: ~11,200
    assert at(s, 70, 2.9) and not at(s, 70, 3.1)
    assert not at(s, -0.5, 0) and not at(s, 140.5, 0)
    assert "Route: 3 m each side of 140 m" in s.reason


def test_out_and_back_is_one_strip():
    single = 6 * 150
    s = build_territory_shape([seg([(0, 0), (150, 0), (0, 0)])])
    check(s)
    assert s.kind == "route" and s.closure_distance_m < 0.01
    # One strip, plus the round join's half disc at the turnaround (pi * 3^2 / 2).
    assert s.area_sq_m == pytest.approx(single + math.pi * 9 / 2, rel=0.005)
    assert "encloses only" in s.reason
    # Return leg 2 m to the side, as GPS would draw it: the 300 m2 sliver is not land.
    s = build_territory_shape([seg([(0, 0), (150, 0), (150, 2), (0, 2), (0, 0)])])
    check(s)
    assert s.kind == "route"
    # An 8 m wide strip (the two legs overlap), plus ~40 m2 of turn and end joins.
    assert 8 * 150 < s.area_sq_m < 8 * 150 + 60
    assert s.area_sq_m < 1.5 * single


def test_figure_eight():
    # Bowtie crossing itself at (50, 50): two triangles of 2,500 m2. Signed area is 0.
    s = build_territory_shape([seg([(0, 0), (100, 100), (100, 0), (0, 100), (0, 0)])])
    check(s)
    assert s.kind == "loop"
    assert s.area_sq_m == pytest.approx(5_000, rel=0.02)
    assert at(s, 80, 50) and at(s, 20, 50)
    assert not at(s, 50, 80) and not at(s, 50, 20)


def test_lollipop():
    loop = [(0, 100), (50, 100), (50, 200), (-50, 200), (-50, 100), (0, 100)]
    s = build_territory_shape([seg([(0, 0)] + loop + [(0, 0)])])
    check(s)
    assert s.kind == "loop"
    assert s.area_sq_m == pytest.approx(10_000, rel=0.02)
    assert not at(s, 0, 50)
    # The return down the stick 2 m off the way out: the sliver is still dropped.
    s = build_territory_shape([seg([(0, 0)] + loop + [(2, 100), (2, 0), (0, 0)])])
    check(s)
    assert s.kind == "loop"
    assert s.area_sq_m == pytest.approx(10_000, rel=0.02)
    assert not at(s, 1, 50)


def test_loop_twice_counts_once():
    s = build_territory_shape([seg(SQUARE + SQUARE[1:])])
    check(s)
    assert s.kind == "loop"
    assert s.area_sq_m == pytest.approx(10_000, rel=0.02)
    # Second lap 2 m inside the first.
    inner = [(2, 2), (98, 2), (98, 98), (2, 98), (2, 2), (0, 0)]
    s = build_territory_shape([seg(SQUARE + inner)])
    check(s)
    assert s.kind == "loop"
    assert s.area_sq_m == pytest.approx(10_000, rel=0.02)


def _segments(result):
    by_id = {}
    for f in result.fixes:
        if f.accepted:
            by_id.setdefault(f.segment_id, []).append((f.lat, f.lng))
    return [by_id[k] for k in sorted(by_id)]


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_noisy_loop(seed):
    fixes, _ = syn.track_400m_loop(seed, noise_m=4.0, laps=1)
    r = process_track(fixes)
    s = build_territory_shape(_segments(r), r.uncertain_distance_m)
    check(s)
    radius = 36.0
    straight = (400 - 2 * math.pi * radius) / 2
    truth = straight * 2 * radius + math.pi * radius ** 2  # 10,329 m2
    assert s.kind == "loop"
    assert s.area_sq_m == pytest.approx(truth, rel=0.05)


def test_noisy_loop_three_laps():
    fixes, _ = syn.track_400m_loop(7, noise_m=4.0, laps=3)
    r = process_track(fixes)
    s = build_territory_shape(_segments(r), r.uncertain_distance_m)
    check(s)
    assert s.kind == "loop"
    # Three noisy laps fill out to the outermost lap, so allow a little more.
    assert 10_329 * 0.95 < s.area_sq_m < 10_329 * 1.12


def _perimeter_points(s0, s1, step=5.0):
    """Points on the 100 m square at perimeter distance s0..s1."""
    def pt(s):
        s %= 400
        if s <= 100:
            return (s, 0.0)
        if s <= 200:
            return (100.0, s - 100)
        if s <= 300:
            return (300 - s, 100.0)
        return (0.0, 400 - s)
    n = int(round((s1 - s0) / step))
    return [ll(*pt(s0 + (s1 - s0) * k / n)) for k in range(n + 1)]


def test_gap_10_percent_is_still_loop():
    # 40 m gap on the east side (perimeter 130..170), bridged by a straight line.
    segs = [_perimeter_points(0, 130), _perimeter_points(170, 400)]
    s = build_territory_shape(segs, uncertain_distance_m=40.0)
    check(s)
    assert s.kind == "loop"
    assert s.area_sq_m == pytest.approx(10_000, rel=0.02)


def test_gap_30_percent_is_route_without_bridge():
    # 120 m gap around the north-east corner (perimeter 140..260).
    segs = [_perimeter_points(0, 140), _perimeter_points(260, 400)]
    s = build_territory_shape(segs, uncertain_distance_m=math.hypot(60, 60))
    check(s)
    assert s.kind == "route"
    assert "gaps are" in s.reason
    assert s.area_sq_m == pytest.approx(280 * 6, rel=0.03)
    assert not at(s, 100, 100)  # the corner the runner was not seen on
    assert not at(s, 70, 70)  # the straight chord across the gap
    assert not at(s, 100, 45) and not at(s, 55, 100)  # flat ends at the gap


def test_gap_120m_reported_as_uncertain_distance():
    segs = [_perimeter_points(0, 140), _perimeter_points(260, 400)]
    s = build_territory_shape(segs, uncertain_distance_m=120.0)
    assert s.kind == "route"


@pytest.mark.parametrize("end_gap, kind", [(20.0, "loop"), (21.0, "route")])
def test_closure_boundary(end_gap, kind):
    s = build_territory_shape([seg([(0, 0), (100, 0), (100, 100), (0, 100), (0, end_gap)])])
    check(s)
    assert s.closure_distance_m == pytest.approx(end_gap, abs=0.01)
    assert s.kind == kind


def test_short_loop_is_route():
    # Closes, but the path is 80 m: under the 100 m loop minimum.
    s = build_territory_shape([seg([(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)])])
    check(s)
    assert s.kind == "route" and "loop minimum" in s.reason


def test_none_cases():
    for segs in ([], [[]], [[ll(0, 0)]], [[ll(0, 0)], []], None):
        s = build_territory_shape(segs)
        check(s)
        assert s.kind == "none" and s.closure_distance_m is None
    # Two fixes in the same place: no movement.
    s = build_territory_shape([[ll(0, 0), ll(0, 0)]])
    check(s)
    assert s.kind == "none" and s.closure_distance_m == pytest.approx(0, abs=1e-6)
    # Single-fix segments contribute no strip.
    s = build_territory_shape([[ll(0, 0)], [ll(50, 0)]], uncertain_distance_m=50)
    check(s)
    assert s.kind == "none"


def test_duplicates_and_custom_config():
    pts = seg([(0, 0), (100, 0)])
    doubled = [p for p in pts for _ in range(3)]
    s = build_territory_shape([doubled])
    check(s)
    assert s.area_sq_m == pytest.approx(600, rel=0.01)
    s = build_territory_shape([pts], config=ShapeConfig(route_half_width_m=5))
    assert s.area_sq_m == pytest.approx(1000, rel=0.01)


def test_jagged_zigzag_route_stays_valid():
    # Hairpins every 3 m, as a bad receiver draws them: no mitre spikes, valid output.
    pts = [ll(3 * k, 4 if k % 2 else -4) for k in range(40)]
    s = build_territory_shape([pts])
    check(s)
    assert s.kind == "route"
    minx, miny, maxx, maxy = s.geometry.bounds
    assert maxy < ll(0, 4 + 3 + 0.5)[0] and miny > ll(0, -4 - 3 - 0.5)[0]
