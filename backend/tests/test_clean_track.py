"""Clean tracks v4 (app/gps/clean_track.py). No database needed.

All coordinates are made up: local metres around (10.0, 20.0).
"""
import math
import random
import time

import pytest
from pyproj import CRS, Transformer
from shapely.geometry import LineString, MultiLineString, Point

from app.gps.clean_track import CleanConfig, CleanTrack, WalkWay, clean_track
from app.gps.geodesy import offset_point
from app.gps.territory_shape import build_territory_shape

LAT0, LNG0 = 10.0, 20.0
_TO_XY = Transformer.from_crs(
    CRS.from_epsg(4326),
    CRS.from_proj4(f"+proj=aeqd +lat_0={LAT0} +lon_0={LNG0} +datum=WGS84 +units=m +no_defs"),
    always_xy=True,
)


def ll(x, y):
    """Local metres (east, north) to (lat, lng)."""
    return offset_point(LAT0, LNG0, x, y)


def xy(p):
    """(lat, lng) to local metres."""
    x, y = _TO_XY.transform(p[1], p[0])
    return float(x), float(y)


def densify(corners, step=3.0):
    out = [corners[0]]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:]):
        n = max(1, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / step)))
        out += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(1, n + 1)]
    return out


def way(osm_id, corners, highway="residential", step=50.0):
    """A way through the given corners, with a node every `step` metres."""
    return WalkWay(osm_id, highway, [ll(x, y) for x, y in densify(corners, step)])


def walk(corners, noise=0.0, zigzag=0.0, seed=1, step=3.0):
    """Fixes every `step` m along the corners, with Gaussian noise or a
    left-right zig-zag of +-zigzag metres across the direction of travel."""
    rng = random.Random(seed)
    pts = densify(corners, step)
    out = []
    for k, (x, y) in enumerate(pts):
        if zigzag:
            a = pts[min(k + 1, len(pts) - 1)]
            b = pts[max(k - 1, 0)]
            dx, dy = a[0] - b[0], a[1] - b[1]
            n = math.hypot(dx, dy) or 1.0
            s = zigzag if k % 2 else -zigzag
            x, y = x - dy / n * s, y + dx / n * s
        x += rng.gauss(0, noise) if noise else 0.0
        y += rng.gauss(0, noise) if noise else 0.0
        out.append(ll(x, y))
    return out


def max_dist(clean_seg, target, step=1.0, trim=0.0):
    """Largest distance (m) from the cleaned line, sampled every `step` m, to
    target, leaving out `trim` m at each end (the ends are the raw first and
    last fixes, or their projections, so they carry the fix's own error)."""
    pts = [xy(p) for p in clean_seg]
    if len(pts) == 1:
        return target.distance(Point(pts[0]))
    line = LineString(pts)
    lo, hi = min(trim, line.length / 2), max(line.length - trim, line.length / 2)
    n = max(1, int((hi - lo) / step))
    return max(target.distance(line.interpolate(lo + (hi - lo) * k / n)) for k in range(n + 1))


def assert_ends_kept(clean_seg, fixes, tol=0.01):
    """The cleaned line starts and ends at the first and last fix."""
    assert math.dist(xy(clean_seg[0]), xy(fixes[0])) < tol
    assert math.dist(xy(clean_seg[-1]), xy(fixes[-1])) < tol


def length_m(clean_seg):
    pts = [xy(p) for p in clean_seg]
    return LineString(pts).length if len(pts) > 1 else 0.0


def check(clean, n_segments):
    assert isinstance(clean, CleanTrack)
    assert len(clean.segments) == n_segments
    assert clean.method in {"matched", "smoothed", "mixed", "raw"}
    assert 0.0 <= clean.matched_fraction <= 1.0
    assert isinstance(clean.notes, str) and clean.notes
    for seg in clean.segments:
        for lat, lng in seg:
            assert math.isfinite(lat) and math.isfinite(lng)


# ---------------------------------------------------------------- matching


def test_zigzag_on_straight_road_comes_out_straight():
    road = way(1, [(-100, 0), (600, 0)])
    fixes = walk([(0, 0), (500, 0)], zigzag=8.0)
    clean = clean_track([fixes], [[8.0] * len(fixes)], [road])
    check(clean, 1)
    assert clean.method == "matched"
    assert clean.matched_fraction > 0.9
    assert max_dist(clean.segments[0], LineString([(-100, 0), (600, 0)])) < 0.5
    assert 480 < length_m(clean.segments[0]) < 520
    assert len(clean.segments[0]) <= 15  # straight road: few points, not one per fix


def test_noisy_walk_with_backsteps_has_no_back_and_forth():
    road = way(1, [(-100, 0), (600, 0)])
    fixes = walk([(0, 0), (400, 0)], noise=5.0, seed=7)
    clean = clean_track([fixes], [[6.0] * len(fixes)], [road])
    assert clean.method == "matched"
    xs = [xy(p)[0] for p in clean.segments[0]]
    assert all(b > a for a, b in zip(xs, xs[1:]))  # always moving forward
    assert max_dist(clean.segments[0], LineString([(-100, 0), (600, 0)])) < 0.5


def test_l_turn_corner_is_at_the_junction():
    ways = [way(1, [(-300, 0), (300, 0)]), way(2, [(0, -300), (0, 300)])]
    fixes = walk([(-200, 0), (0, 0), (0, 200)], noise=4.0, seed=3)
    clean = clean_track([fixes], [[6.0] * len(fixes)], ways)
    check(clean, 1)
    assert clean.method == "matched"
    pts = [xy(p) for p in clean.segments[0]]
    assert min(math.hypot(x, y) for x, y in pts) < 0.5  # a vertex on the junction
    assert max_dist(clean.segments[0], LineString([(-300, 0), (0, 0), (0, 300)])) < 0.5
    # It goes east then north, without wandering up the other arms.
    assert all(x <= 0.5 for x, _ in pts) and all(y >= -0.5 for _, y in pts)


def test_parallel_road_40m_away_is_not_chosen():
    ways = [way(1, [(-100, 0), (600, 0)]), way(2, [(-100, 40), (600, 40)])]
    fixes = walk([(0, 0), (500, 0)], noise=6.0, seed=11)
    clean = clean_track([fixes], [[8.0] * len(fixes)], ways)
    assert clean.method == "matched"
    assert max_dist(clean.segments[0], LineString([(-100, 0), (600, 0)])) < 0.5


def test_closed_block_loop_still_scores_as_loop():
    ways = [
        way(1, [(-100, 0), (300, 0)]), way(2, [(-100, 200), (300, 200)]),
        way(3, [(0, -100), (0, 300)]), way(4, [(200, -100), (200, 300)]),
    ]
    corners = [(0, 0), (200, 0), (200, 200), (0, 200), (0, 0)]
    fixes = walk(corners, noise=5.0, seed=5)
    clean = clean_track([fixes], [[6.0] * len(fixes)], ways)
    assert clean.method == "matched"
    streets = MultiLineString([[xy(p) for p in w.points] for w in ways])
    assert max_dist(clean.segments[0], streets) < 0.5
    assert max_dist(clean.segments[0], LineString(corners), trim=10.0) < 0.5
    shape = build_territory_shape(clean.segments)
    assert shape.kind == "loop"
    assert 38_000 < shape.area_sq_m < 42_000


# ---------------------------------------------------------------- off-network


def test_park_crossing_is_smoothed_not_snapped_to_the_edge_road():
    edge_road = way(1, [(-100, 0), (400, 0)])
    true = LineString([(0, 20), (150, 150), (300, 20)])
    fixes = walk(list(true.coords), noise=3.0, seed=2)
    clean = clean_track([fixes], [[4.0] * len(fixes)], [edge_road])
    check(clean, 1)
    assert clean.matched_fraction < 0.1
    assert clean.method in {"smoothed", "mixed"}
    assert max_dist(clean.segments[0], true, trim=5.0) < 5.0
    assert min(xy(p)[1] for p in clean.segments[0]) > 10  # never pulled onto the road
    assert_ends_kept(clean.segments[0], fixes)


def test_runner_on_a_park_trail_beside_a_road_stays_on_the_trail():
    """20 m inside the park, with good accuracy: too far to trust the road."""
    road = way(1, [(-100, 0), (400, 0)])
    true = LineString([(0, 20), (300, 20)])
    fixes = walk(list(true.coords), noise=2.0, seed=4)
    clean = clean_track([fixes], [[4.0] * len(fixes)], [road])
    assert clean.matched_fraction < 0.1
    assert max_dist(clean.segments[0], true, trim=5.0) < 4.0


def test_road_then_park_then_road_is_mixed():
    ways = [
        way(1, [(0, 0), (600, 0)]),
        way(2, [(300, 200), (600, 200)]),
        way(3, [(600, 0), (600, 200)]),
    ]
    true = LineString([(0, 0), (300, 0), (300, 200), (550, 200)])
    fixes = walk(list(true.coords), noise=3.0, seed=8)
    clean = clean_track([fixes], [[5.0] * len(fixes)], ways)
    check(clean, 1)
    assert clean.method == "mixed"
    assert 0.5 < clean.matched_fraction < 0.9
    assert max_dist(clean.segments[0], true) < 5.0
    # The park stretch was not routed round by the roads.
    assert 700 < length_m(clean.segments[0]) < 800


def test_no_ways_gives_smoothed_line():
    fixes = walk([(0, 0), (300, 0), (300, 200)], zigzag=8.0)
    clean = clean_track([fixes], [[8.0] * len(fixes)], [])
    check(clean, 1)
    assert clean.method == "smoothed"
    assert clean.matched_fraction == 0.0
    assert max_dist(clean.segments[0], LineString([(0, 0), (300, 0), (300, 200)]), trim=15.0) < 4.0
    assert len(clean.segments[0]) < len(fixes) / 10
    assert_ends_kept(clean.segments[0], fixes)
    # The corner is kept.
    pts = [xy(p) for p in clean.segments[0]]
    assert min(math.hypot(x - 300, y) for x, y in pts) < 5.0


# ---------------------------------------------------------------- structure and robustness


def test_segments_are_kept_and_never_joined():
    road = way(1, [(-100, 0), (900, 0)])
    a = walk([(0, 0), (300, 0)], noise=3.0, seed=1)
    b = walk([(500, 0), (800, 0)], noise=3.0, seed=2)
    single = [ll(400, 0)]
    segs = [a, [], single, b]
    accs = [[5.0] * len(a), [], [5.0], [5.0] * len(b)]
    clean = clean_track(segs, accs, [road])
    check(clean, 4)
    assert clean.segments[1] == [] and clean.segments[2] == single
    first, last = clean.segments[0], clean.segments[3]
    assert xy(first[-1])[0] < 310 and xy(last[0])[0] > 490  # the gap stays a gap
    assert 280 < length_m(first) < 320 and 280 < length_m(last) < 320


def test_empty_and_tiny_inputs():
    road = way(1, [(0, 0), (100, 0)])
    empty = clean_track([], [], [road])
    assert empty.segments == [] and empty.method == "raw" and empty.matched_fraction == 0.0
    one = clean_track([[ll(0, 0)]], [[None]], [road])
    assert one.segments == [[ll(0, 0)]] and one.method == "raw"
    blank = clean_track([[]], [[]], [])
    assert blank.segments == [[]] and blank.method == "raw"
    two = clean_track([[ll(0, 2), ll(10, -2)]], [[5.0, 5.0]], [road])
    check(two, 1)
    assert len(two.segments[0]) >= 2


def test_bad_inputs_do_not_break_it():
    fixes = walk([(0, 0), (200, 0)], noise=3.0)
    fixes = fixes[:10] + [fixes[9]] * 5 + fixes[10:]  # standing still: duplicate fixes
    accs = [None, float("nan"), -1.0] + [5.0] * (len(fixes) - 10)  # short list, odd values
    ways = [
        WalkWay(1, "residential", [ll(0, 0)]),  # one point
        WalkWay(2, "residential", []),  # no points
        WalkWay(3, "residential", [ll(0, 0), ll(0, 0)]),  # zero length
        WalkWay(4, "residential", [(LAT0 + 1.0, LNG0), (LAT0 + 1.0, LNG0 + 0.01)]),  # 110 km away
        WalkWay(5, "motorway", [ll(-100, 0), ll(300, 0)]),  # not walkable
    ]
    clean = clean_track([fixes], [accs], ways)
    check(clean, 1)
    assert clean.method == "smoothed"
    assert max_dist(clean.segments[0], LineString([(0, 0), (200, 0)]), trim=15.0) < 4.0


def test_smoothing_keeps_square_corners():
    """No ways: a walked square keeps its corners, so it keeps its area."""
    corners = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]
    exact = clean_track([walk(corners)], [[5.0] * 134], [])
    pts = [xy(p) for p in exact.segments[0]]
    assert len(pts) == 5
    assert max(min(math.dist(p, c) for p in pts) for c in corners) < 0.5
    noisy = walk(corners, noise=3.0, seed=3)
    shape = build_territory_shape(clean_track([noisy], [[5.0] * len(noisy)], []).segments)
    assert shape.kind == "loop"
    assert shape.area_sq_m == pytest.approx(10_000, rel=0.03)


def test_smoothing_keeps_the_length_of_a_straight_track():
    """No ways: the ends are kept, so a straight track is not shortened."""
    fixes = walk([(0, 0), (141, 0)], noise=2.0, seed=12)
    clean = clean_track([fixes], [[5.0] * len(fixes)], [])
    assert clean.method == "smoothed"
    assert_ends_kept(clean.segments[0], fixes)
    assert abs(length_m(clean.segments[0]) - math.dist(xy(fixes[0]), xy(fixes[-1]))) < 3.0


def test_matched_line_starts_and_ends_at_the_projected_first_and_last_fix():
    road = way(1, [(-100, 0), (600, 0)])
    fixes = walk([(0, 0), (300, 0)], noise=3.0, seed=13)
    clean = clean_track([fixes], [[5.0] * len(fixes)], [road])
    assert clean.method == "matched"
    first, last = xy(clean.segments[0][0]), xy(clean.segments[0][-1])
    assert abs(first[0] - xy(fixes[0])[0]) < 0.01 and abs(first[1]) < 0.01
    assert abs(last[0] - xy(fixes[-1])[0]) < 0.01 and abs(last[1]) < 0.01


def test_link_and_footway_types_are_used():
    for hw in ("footway", "primary_link", "steps", "corridor"):
        clean = clean_track([walk([(0, 0), (200, 0)], zigzag=5.0)], [[None] * 67],
                            [way(1, [(-50, 0), (250, 0)], highway=hw)])
        assert clean.method == "matched", hw


def test_config_is_frozen():
    with pytest.raises(Exception):
        CleanConfig().max_snap_m = 50.0  # type: ignore[misc]


# ---------------------------------------------------------------- speed


def test_5km_run_with_2000_ways_is_fast():
    ways = []
    n = 31  # streets every 100 m over 3 km, each split per block: 1,860 ways
    for i in range(n):
        for j in range(n - 1):
            ways.append(WalkWay(len(ways), "residential", [ll(i * 100, j * 100), ll(i * 100, (j + 1) * 100)]))
            ways.append(WalkWay(len(ways), "residential", [ll(j * 100, i * 100), ll((j + 1) * 100, i * 100)]))
    for k in range(140):  # and some footpaths through the blocks
        x = 50 + (k % 30) * 100
        ways.append(WalkWay(len(ways), "footway", [ll(x, (k // 30) * 600), ll(x, (k // 30) * 600 + 100)]))
    assert len(ways) >= 2000
    corners = [(200, 200), (1200, 200), (1200, 1200), (2200, 1200), (2200, 2200), (1200, 2200),
               (1200, 2700)]
    fixes = walk(corners, noise=5.0, seed=9, step=3.4)
    assert 1400 <= len(fixes) <= 1700
    accs = [[6.0] * len(fixes)]
    t0 = time.perf_counter()
    clean = clean_track([fixes], accs, ways)
    elapsed = time.perf_counter() - t0
    assert elapsed < 4.0, f"took {elapsed:.2f} s"
    assert clean.method == "matched"
    streets = MultiLineString([[(w_xy[0], w_xy[1]) for w_xy in map(xy, w.points)] for w in ways])
    assert max_dist(clean.segments[0], streets, step=5.0) < 0.5  # on the network throughout
    assert max_dist(clean.segments[0], LineString(corners), step=5.0) < 2.0  # and on the runner's streets
    assert abs(length_m(clean.segments[0]) - LineString(corners).length) < 50
