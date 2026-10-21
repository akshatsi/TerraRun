"""Territory shape rules v2 (app/gps/territory_shape.py). No database needed."""
import math
import random
import re

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


def enclosed(shape):
    """The enclosed area the reason reports, in m2 (0 if none)."""
    m = re.search(r"([\d,]+) m² enclosed", shape.reason)
    return float(m.group(1).replace(",", "")) if m else 0.0


SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]


def test_square_loop():
    s = build_territory_shape([seg([(0, 0), (100, 0), (100, 100), (0, 100), (0, 4)])])
    check(s)
    assert s.kind == "loop"
    assert s.closure_distance_m == pytest.approx(4, abs=0.01)
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    assert "Loop closed 4 m" in s.reason
    # Only the enclosed area: no corridor along the loop's own edge.
    assert s.area_sq_m == pytest.approx(10_000, rel=0.02)
    assert at(s, 50, 50) and not at(s, 50, -1)


def test_square_ending_30m_away_is_loop():
    s = build_territory_shape([seg([(0, 0), (100, 0), (100, 100), (0, 100), (0, 30)])])
    check(s)
    assert s.kind == "loop"
    assert s.closure_distance_m == pytest.approx(30, abs=0.01)
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    assert "Loop closed 30 m from start" in s.reason
    assert s.area_sq_m == pytest.approx(10_000, rel=0.02)
    assert at(s, 1, 15) and not at(s, -1, 15) and not at(s, -1, 50)


RECT = [(0, 0), (400, 0), (400, 300), (0, 300)]


@pytest.mark.parametrize("end", [25.0, 150.0, 199.0, 200.0])
def test_end_within_200m_closes_loop(end):
    s = build_territory_shape([seg(RECT + [(0, end)])])
    check(s)
    assert s.closure_distance_m == pytest.approx(end, abs=0.01)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(120_000, rel=0.01)
    assert f"Loop closed {end:.0f} m from start" in s.reason
    assert at(s, 200, 150) and at(s, 5, end / 2)


def test_end_201m_away_is_not_joined():
    s = build_territory_shape([seg(RECT + [(0, 201)])])
    check(s)
    assert s.kind == "route"
    assert "ended 201 m from start (a loop needs 200 m or less)" in s.reason
    assert s.area_sq_m == pytest.approx((400 + 300 + 400 + 99) * 6, rel=0.03)
    assert not at(s, 200, 150)


def test_join_must_be_short_against_path():
    # Long, thin out-and-back ending 150 m from the start: the join would be
    # 33% of the 460 m path, over the 25% limit.
    s = build_territory_shape([seg([(0, 0), (300, 0), (300, 10), (150, 10)])])
    check(s)
    assert s.kind == "route"
    assert s.closure_distance_m == pytest.approx(150.3, abs=0.1)
    assert "over 25% of the 460 m path" in s.reason
    assert not at(s, 75, 4.5)
    # Wider, so only the ratio stops it: allowed a 50% join it would be a loop.
    wide = [seg([(0, 0), (300, 0), (300, 40), (150, 40)])]
    s = build_territory_shape(wide)
    assert s.kind == "route" and "over 25%" in s.reason
    s = build_territory_shape(wide, config=ShapeConfig(max_closure_fraction=0.5))
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(150 * 40 * 1.5, rel=0.03)


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
    # Legs 10 m apart, as on two pavements: within the snap distance and the
    # join, but no wider than it, so still not land.
    s = build_territory_shape([seg([(0, 0), (300, 0), (300, 10), (0, 10)])])
    check(s)
    assert s.kind == "route"
    assert not at(s, 150, 5)


def test_figure_eight():
    # Bowtie crossing itself at (50, 50): two triangles of 2,500 m2. Signed area is 0.
    s = build_territory_shape([seg([(0, 0), (100, 100), (100, 0), (0, 100), (0, 0)])])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(5_000, rel=0.02)
    assert at(s, 80, 50) and at(s, 20, 50)
    assert not at(s, 50, 80) and not at(s, 50, 20)


def test_lollipop():
    loop = [(0, 100), (50, 100), (50, 200), (-50, 200), (-50, 100), (0, 100)]
    s = build_territory_shape([seg([(0, 0)] + loop + [(0, 0)])])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    assert at(s, 0, 150) and at(s, 2, 50)  # the stick earns its route strip
    assert not at(s, 4, 50)
    # The return down the stick 2 m off the way out: the sliver is still dropped.
    s = build_territory_shape([seg([(0, 0)] + loop + [(2, 100), (2, 0), (0, 0)])])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    assert at(s, 1, 50) and not at(s, 6, 50)


def test_lollipop_long_stick_legs_apart():
    # 300 m stick, back 8 m to the side; the loop does not quite close (8 m)
    # and the run ends 8 m from the start. Only the loop is land.
    out = [(0, 0), (0, 300), (50, 300), (50, 400), (-50, 400), (-50, 300), (-8, 300), (-8, 0)]
    s = build_territory_shape([seg(out)])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(10_000, rel=0.03)
    assert at(s, 0, 350)
    assert at(s, 0, 150) and at(s, -8, 150)  # both legs of the stick as route
    assert not at(s, -4, 150)  # the 8 m between them is not land


def test_figure_six_tail_and_crossing():
    # Stem down from (0, 300), a loop at the bottom that crosses the stem at (0, 100).
    s = build_territory_shape([seg([(0, 300), (0, 0), (100, 0), (100, 100), (-20, 100)])])
    check(s)
    assert s.kind == "loop"
    assert s.closure_distance_m > 200
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    assert s.reason.startswith("Path crossed itself;")
    assert "m of route" in s.reason
    assert at(s, 50, 50) and at(s, 0, 200) and at(s, -15, 100)
    assert not at(s, 10, 200)


def test_crossing_mid_run_without_return():
    # East, north, west, then south through the first leg at (100, 0), then on east.
    pts = [(0, 0), (200, 0), (200, 100), (100, 100), (100, -100), (300, -100)]
    s = build_territory_shape([seg(pts)])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    assert "Path crossed itself; " in s.reason
    tail = 100 + 100 + 200  # first 100 m east; 100 m south and 200 m east after
    assert s.area_sq_m == pytest.approx(10_000 + 6 * tail, rel=0.05)
    assert at(s, 150, 50) and at(s, 50, 0) and at(s, 200, -100)
    assert not at(s, 150, -50)


def test_near_miss_closes():
    # Round the square and back to 10 m from the start without crossing
    # (390 m along the path), then away west. The end is 300 m from the start.
    pts = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 10), (-300, 10)]
    s = build_territory_shape([seg(pts)])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    assert "Path came back within 15 m of itself" in s.reason
    assert at(s, 50, 50) and at(s, -150, 10)
    # Without snapping, or with the miss wider than the snap distance: a route.
    s = build_territory_shape([seg(pts)], config=ShapeConfig(self_snap_m=0))
    assert s.kind == "route"
    far = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 20), (-300, 20)]
    assert build_territory_shape([seg(far)]).kind == "route"


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_straight_jitter_is_route(seed):
    rng = random.Random(seed)
    pts = [ll(3 * k + rng.gauss(0, 3), rng.gauss(0, 3)) for k in range(334)]
    s = build_territory_shape([pts])
    check(s)
    assert s.kind == "route"
    assert "enclosed" not in s.reason


def test_gentle_s_curve_is_route():
    pts = [(x, 50 * math.sin(2 * math.pi * x / 400)) for x in range(0, 801, 4)]
    s = build_territory_shape([seg(pts)])
    check(s)
    assert s.kind == "route"
    assert "ended" in s.reason


def test_loop_twice_counts_once():
    s = build_territory_shape([seg(SQUARE + SQUARE[1:])])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    # Second lap 2 m inside the first.
    inner = [(2, 2), (98, 2), (98, 98), (2, 98), (2, 2), (0, 0)]
    s = build_territory_shape([seg(SQUARE + inner)])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    # Second lap 10 m inside: the ring between laps is the runner's anyway.
    inner = [(10, 10), (90, 10), (90, 90), (10, 90), (10, 10), (0, 0)]
    s = build_territory_shape([seg(SQUARE + inner)])
    check(s)
    assert s.kind == "loop"
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)


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
    assert enclosed(s) == pytest.approx(truth, rel=0.05)
    assert s.area_sq_m >= enclosed(s) - 1


def test_noisy_loop_three_laps():
    fixes, _ = syn.track_400m_loop(7, noise_m=4.0, laps=3)
    r = process_track(fixes)
    s = build_territory_shape(_segments(r), r.uncertain_distance_m)
    check(s)
    assert s.kind == "loop"
    # Three noisy laps fill out to the outermost lap, so allow a little more.
    assert 10_329 * 0.95 < enclosed(s) < 10_329 * 1.12


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
    assert enclosed(s) == pytest.approx(10_000, rel=0.02)
    assert not at(s, 101.5, 10) and not at(s, 101.5, 50)  # no corridor, none across the gap


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


@pytest.mark.parametrize("end_gap, kind", [(200.0, "loop"), (201.0, "route")])
def test_closure_boundary(end_gap, kind):
    s = build_territory_shape([seg(RECT + [(0, end_gap)])])
    check(s)
    assert s.closure_distance_m == pytest.approx(end_gap, abs=0.01)
    assert s.kind == kind


def test_short_loop_is_route():
    # Closes, but the path is 80 m: under the 100 m loop minimum.
    s = build_territory_shape([seg([(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)])])
    check(s)
    assert s.kind == "route" and "loop minimum" in s.reason
    # The same 80 m square crossed mid-run is still under the loop minimum.
    s = build_territory_shape([seg([(-50, 0), (20, 0), (20, 20), (10, 20), (10, -50)])])
    check(s)
    assert s.kind == "route"


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
