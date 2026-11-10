"""Route finder (app/routing/planner.py). No database needed: synthetic street grids."""
import math
import time

import pytest
from pyproj import Geod
from shapely.geometry import LineString, Polygon

from app.gps.geodesy import distance_m, offset_point
from app.gps.territory_shape import build_territory_shape
from app.routing import OwnedArea, PlannerConfig, PlannerInput, RoadWay, Suggestion, plan_routes
from app.routing.blocks import section_multipliers
from app.routing.graph import LocalFrame

LAT0, LNG0 = 26.9342, 75.9241
GEOD = Geod(ellps="WGS84")
FRAME = LocalFrame(LAT0, LNG0)
ME, FRIEND, OTHER_FRIEND = 1, 7, 9


def ll(x, y):
    """Local metres (east, north) from the origin to (lat, lng)."""
    return offset_point(LAT0, LNG0, x, y)


def xy(lat_lng):
    return tuple(FRAME.to_xy([lat_lng])[0])


def street(points, highway="residential", osm_id=1, step=50.0):
    """A RoadWay through local-metre corners, with a point every `step` metres."""
    out = [points[0]]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        n = max(1, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / step)))
        out += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(1, n + 1)]
    return RoadWay(osm_id=osm_id, highway=highway, points=[ll(x, y) for x, y in out])


def grid(nx, ny, block=100.0, x0=0.0, y0=0.0, highway="residential", first_id=1):
    """nx x ny blocks of `block` metres; one way per full street."""
    roads, oid = [], first_id
    for j in range(ny + 1):
        y = y0 + j * block
        roads.append(street([(x0, y), (x0 + nx * block, y)], highway, oid))
        oid += 1
    for i in range(nx + 1):
        x = x0 + i * block
        roads.append(street([(x, y0), (x, y0 + ny * block)], highway, oid))
        oid += 1
    return roads


def square(x0, y0, x1, y1):
    """WGS-84 polygon (x=lng, y=lat) of a local-metre rectangle."""
    pts = [ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1)]
    return Polygon([(p[1], p[0]) for p in pts])


def garea(geom):
    total = 0.0
    for p in getattr(geom, "geoms", [geom]):
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        a, _ = GEOD.geometry_area_perimeter(p)
        total += abs(a)
    return total


def plan(roads, target, start=(250.0, 250.0), mine=None, friends=(), popularity=None, config=None):
    inp = PlannerInput(
        start=ll(*start),
        roads=roads,
        my_user_id=ME,
        my_territory=OwnedArea(ME, mine) if mine is not None else None,
        friend_territories=list(friends),
        target_distance_m=target,
        popularity=popularity or {},
    )
    return plan_routes(inp, config or PlannerConfig())


def centroid_xy(s: Suggestion):
    return xy((s.enclosed.centroid.y, s.enclosed.centroid.x))


def by_label(out, label):
    found = [s for s in out if s.label == label]
    return found[0] if found else None


def split_leg(local, approach_m):
    """The loop part of a route in local metres, after checking the leg back retraces the leg out."""
    if approach_m == 0:
        return local
    cum, i = 0.0, 0
    while cum < approach_m - 0.01:
        cum += math.dist(local[i], local[i + 1])
        i += 1
    assert cum == pytest.approx(approach_m, abs=0.01)
    n = len(local)
    for j in range(i + 1):
        assert math.dist(local[j], local[n - 1 - j]) < 0.01
    return local[i:n - i]


def check_suggestion(s: Suggestion, start, target, cfg=PlannerConfig()):
    assert s.route[0] == s.route[-1]
    assert distance_m(*ll(*start), *s.route[0]) <= cfg.start_radius_m + 1.0
    assert (1 - cfg.distance_tolerance) * target - 1 <= s.distance_m <= (1 + cfg.distance_tolerance) * target + 1
    lats, lngs = [p[0] for p in s.route], [p[1] for p in s.route]
    assert s.distance_m == pytest.approx(GEOD.line_length(lngs, lats), rel=1e-6)
    # The route is a leg out, a loop that never touches itself, and the same leg back.
    local = [xy(p) for p in s.route]
    loop = split_leg(local, s.approach_m)
    assert loop[0] == loop[-1]
    assert LineString(loop).is_simple
    # The territory rules award it as a loop, and the gains add up.
    shape = build_territory_shape([s.route])
    assert shape.kind == "loop"
    assert garea(s.enclosed) == pytest.approx(shape.area_sq_m, rel=1e-6)
    assert s.gain_sq_m == pytest.approx(s.new_area_sq_m + s.stolen_area_sq_m)
    assert s.stolen_area_sq_m == pytest.approx(sum(s.stolen_by_user.values()))
    assert s.new_area_sq_m + s.stolen_area_sq_m + s.already_mine_sq_m == pytest.approx(shape.area_sq_m, rel=1e-6)
    # Enclosed land is the blocks inside the loop: the route's own polygon,
    # and a whole number of 100 m blocks on these grids.
    # The leg earns its 3 m strip each side on top.
    ring_area = Polygon(loop).area
    strip = 2 * 3.0 * s.approach_m
    assert shape.area_sq_m == pytest.approx(ring_area + strip, rel=0.01, abs=50)
    assert ring_area / 10_000 == pytest.approx(round(ring_area / 10_000), rel=0.01)
    assert s.reason and "\n" not in s.reason


# ---------------------------------------------------------------- basics


def test_loops_start_near_runner_and_fit_target():
    out = plan(grid(5, 5), 1600)
    assert 1 <= len(out) <= 3
    assert len({s.label for s in out}) == len(out)
    assert all(s.label in {"Most new land", "Most from friends", "Closest to your usual run"} for s in out)
    for s in out:
        check_suggestion(s, (250, 250), 1600)
        assert s.stolen_area_sq_m == 0 and s.already_mine_sq_m == 0
    scores = [s.score for s in out]
    assert scores == sorted(scores, reverse=True)
    # The runner stands on the grid, so no loop needs a leg out to it.
    assert any(s.approach_m == 0 for s in out)


def test_runner_mid_block_and_off_centre():
    out = plan(grid(6, 4), 1200, start=(130, 60))
    assert out
    for s in out:
        check_suggestion(s, (130, 60), 1200)


def test_suggestions_differ():
    out = plan(grid(8, 8), 1600, start=(400, 400))
    assert len(out) >= 2
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            inter = garea(a.enclosed.intersection(b.enclosed))
            union = garea(a.enclosed.union(b.enclosed))
            assert inter / union <= PlannerConfig().max_overlap + 0.02


def test_target_sets_loop_size():
    small = plan(grid(5, 5), 400)
    large = plan(grid(5, 5), 1600)
    assert small and large
    for s in small:
        check_suggestion(s, (250, 250), 400)
        assert s.distance_m <= 500 + 1
    for s in large:
        check_suggestion(s, (250, 250), 1600)
        assert s.distance_m >= 1200 - 1
    assert min(garea(s.enclosed) for s in large) > max(garea(s.enclosed) for s in small)


def test_closest_label_is_near_target():
    out = plan(grid(10, 10), 1600, start=(500, 500))
    closest = by_label(out, "Closest to your usual run")
    assert closest is not None
    assert abs(closest.distance_m - 1600) <= 0.15 * 1600


# ---------------------------------------------------------------- whose land


def test_friend_land_draws_most_from_friends():
    friend_land = square(300, 0, 500, 500)  # the two eastern columns
    out = plan(grid(5, 5), 1200, friends=[OwnedArea(FRIEND, friend_land)])
    top = by_label(out, "Most from friends")
    assert top is not None
    check_suggestion(top, (250, 250), 1200)
    assert centroid_xy(top)[0] > 250
    assert set(top.stolen_by_user) == {FRIEND}
    expect = garea(top.enclosed.intersection(friend_land))
    assert expect > 5_000
    assert top.stolen_by_user[FRIEND] == pytest.approx(expect, rel=1e-3, abs=1.0)
    assert top.stolen_area_sq_m == pytest.approx(expect, rel=1e-3, abs=1.0)
    assert "from friends" in top.reason
    for s in out:
        check_suggestion(s, (250, 250), 1200)


def test_stolen_is_split_per_friend():
    a = square(300, 0, 500, 500)
    b = square(0, 0, 200, 500)
    out = plan(grid(5, 5), 2000, friends=[OwnedArea(FRIEND, a), OwnedArea(OTHER_FRIEND, b)])
    assert out
    for s in out:
        check_suggestion(s, (250, 250), 2000)
        for uid, geom in ((FRIEND, a), (OTHER_FRIEND, b)):
            expect = garea(s.enclosed.intersection(geom))
            assert s.stolen_by_user.get(uid, 0.0) == pytest.approx(expect, rel=1e-3, abs=1.0)


def test_own_land_is_not_gain_and_pulls_loops_away():
    mine = square(0, 0, 300, 600)  # west half of a 6 x 6 grid
    out = plan(grid(6, 6), 1200, start=(300, 250), mine=mine)
    assert out
    for s in out:
        check_suggestion(s, (300, 250), 1200)
        held = garea(s.enclosed.intersection(mine))
        assert s.already_mine_sq_m == pytest.approx(held, rel=1e-3, abs=1.0)
        assert s.new_area_sq_m == pytest.approx(garea(s.enclosed) - held, rel=1e-3, abs=1.0)
        assert s.gain_sq_m >= PlannerConfig().min_gain_sq_m
    new = by_label(out, "Most new land")
    assert new is not None
    assert new.already_mine_sq_m < 0.1 * garea(new.enclosed)
    assert centroid_xy(new)[0] > 300


def test_runner_holding_everything_gets_nothing():
    mine = square(-50, -50, 550, 550)
    assert plan(grid(5, 5), 1200, mine=mine) == []


def test_only_friends_count_as_rivals():
    # Anyone else's land is not an input, so it is plain new land; and the
    # runner's own id among "friends" is never treated as a friend.
    own_as_friend = OwnedArea(ME, square(300, 0, 500, 500))
    out = plan(grid(5, 5), 1200, friends=[own_as_friend])
    assert out
    for s in out:
        assert s.stolen_area_sq_m == 0
        assert s.stolen_by_user == {}
        assert s.new_area_sq_m == pytest.approx(garea(s.enclosed), rel=1e-6)
    assert by_label(out, "Most from friends") is None


def test_section_focus_bonus():
    size = 250.0
    # 10% of section (0, 0) held -> bonus; a fully held and an empty section -> none.
    some = Polygon([(-125, -125), (125, -125), (125, -100), (-125, -100)])
    full = Polygon([(125, -125), (375, -125), (375, 125), (125, 125)])
    sections, _ = section_multipliers(some.union(full), 400, size, 0.05, 0.6, 1.15)
    assert sections.get((0, 0)) == 1.15
    assert (1, 0) not in sections
    assert (-1, 0) not in sections


# ---------------------------------------------------------------- road network shape


def campus(spur_from=(20.0, 0.0), grid_x0=300.0):
    """The runner on a campus: only dead-end service roads near them, a spur
    out to a grid of streets 300-700 m east (the campus paths are footways and
    never reach the planner)."""
    roads = grid(4, 4, x0=grid_x0, y0=-200.0, first_id=100)
    roads.append(street([spur_from, (grid_x0, 0.0)], "service", 1))
    roads.append(street([(60.0, 0.0), (60.0, 80.0)], "service", 2))  # dead-end branches
    roads.append(street([(120.0, 0.0), (120.0, -90.0)], "service", 3))
    return roads


def test_runner_away_from_loops_gets_an_approach_leg():
    out = plan(campus(), 1600, start=(0, 0))
    assert out
    for s in out:
        check_suggestion(s, (0, 0), 1600)
        # Out along the spur (it starts at the road point nearest the runner,
        # 20 m away), round a loop in the grid, and back the same way.
        assert s.approach_m == pytest.approx(280.0, abs=1.0)
        local = [xy(p) for p in s.route]
        assert local[0] == pytest.approx((20.0, 0.0), abs=0.5)
        assert all(abs(y) < 0.5 for x, y in local if x < 299.0)
        assert max(x for x, _ in local) > 400.0
        loop = split_leg(local, s.approach_m)
        assert min(x for x, _ in loop) >= 300.0 - 0.5
        assert "away by road" in s.reason


def test_approach_leg_limits():
    # The nearest road is beyond start_radius_m: nothing.
    assert plan(campus(spur_from=(200.0, 0.0)), 1600, start=(0, 0)) == []
    # Loops further than the leg allows (35% of the target): nothing.
    assert plan(campus(grid_x0=700.0), 1600, start=(0, 0)) == []
    cfg = PlannerConfig(max_access_m=200.0)
    assert plan(campus(), 1600, start=(0, 0), config=cfg) == []


def test_tree_of_dead_ends_returns_empty():
    roads = [street([(0, 0), (600, 0)], osm_id=1)]
    roads += [street([(x, 0), (x, 200)], osm_id=10 + i) for i, x in enumerate(range(0, 601, 100))]
    roads += [street([(300, 200), (300, 400)], osm_id=50), street([(250, 400), (350, 400)], osm_id=51)]
    assert plan(roads, 1200, start=(300, 100)) == []


def test_no_roads_or_bad_input_returns_empty():
    assert plan([], 1200) == []
    assert plan(grid(5, 5), 0) == []
    assert plan(grid(5, 5), float("nan")) == []


def test_disconnected_roads_are_ignored():
    near = grid(3, 3)  # 0..300
    island = grid(3, 3, x0=450, first_id=100)  # 150 m east, never joined
    out = plan(near + island, 1200, start=(150, 150))
    assert out
    for s in out:
        check_suggestion(s, (150, 150), 1200)
        assert all(xy(p)[0] <= 300 + 1 for p in s.route)
    # Roads far beyond the search area only: nothing.
    far = grid(5, 5, x0=4000, y0=4000)
    assert plan(far, 1200, start=(150, 150)) == []


def test_small_gaps_in_road_data_are_closed():
    # Every north-south street stops 3 m short of the east-west streets.
    roads = [street([(0, y), (500, y)], osm_id=1 + j) for j, y in enumerate(range(0, 501, 100))]
    roads += [street([(x, 3), (x, 497)], osm_id=20 + i) for i, x in enumerate(range(0, 501, 100))]
    out = plan(roads, 1200)
    assert out
    for s in out:
        check_suggestion(s, (250, 250), 1200)


def test_bigger_roads_break_ties():
    # Two identical blocks either side of the runner; the eastern one is
    # bounded by primary roads.
    def roads(east_hw, west_hw):
        return [
            street([(0, 0), (0, 100)], "residential", 1),
            street([(-100, 0), (0, 0)], west_hw, 2),
            street([(-100, 100), (0, 100)], west_hw, 3),
            street([(-100, 0), (-100, 100)], west_hw, 4),
            street([(0, 0), (100, 0)], east_hw, 5),
            street([(0, 100), (100, 100)], east_hw, 6),
            street([(100, 0), (100, 100)], east_hw, 7),
        ]

    east = plan(roads("primary", "residential"), 400, start=(0, 50))
    west = plan(roads("residential", "primary"), 400, start=(0, 50))
    assert east and west
    assert centroid_xy(east[0])[0] > 0
    assert centroid_xy(west[0])[0] < 0
    assert east[0].new_area_sq_m == pytest.approx(west[0].new_area_sq_m, rel=1e-6)


def test_friends_popular_roads_break_ties():
    roads = grid(2, 1, x0=-100)  # blocks west and east of x = 0
    east_ids = {r.osm_id for r in roads if min(xy(p)[0] for p in r.points) >= -1}
    out = plan(roads, 400, start=(0, 50), popularity={i: 5 for i in east_ids})
    assert out and centroid_xy(out[0])[0] > 0


# ---------------------------------------------------------------- determinism and speed


def test_same_input_same_output():
    friends = [OwnedArea(FRIEND, square(300, 0, 500, 500))]
    mine = square(0, 0, 100, 200)
    a = plan(grid(8, 8), 1600, start=(370, 410), mine=mine, friends=friends)
    b = plan(grid(8, 8), 1600, start=(370, 410), mine=mine, friends=friends)
    assert a
    assert [(s.label, s.route, s.distance_m, s.gain_sq_m) for s in a] == \
        [(s.label, s.route, s.distance_m, s.gain_sq_m) for s in b]


@pytest.mark.parametrize("target", [2000, 4000])
def test_large_grid_is_fast(target):
    roads = grid(20, 20)  # 2 km x 2 km, 840 street pieces
    friends = [OwnedArea(FRIEND, square(1000, 1000, 1600, 1600))]
    mine = square(800, 800, 1000, 1100)
    plan(grid(2, 2), 400)  # warm up imports and projections
    t = time.perf_counter()
    out = plan(roads, target, start=(1050, 1050), mine=mine, friends=friends)
    elapsed = time.perf_counter() - t
    assert out
    assert elapsed < 2.0, f"took {elapsed:.2f} s"
    for s in out:
        check_suggestion(s, (1050, 1050), target)


# --- honest labels -----------------------------------------------------------

def test_labels_are_true_among_the_suggestions_shown():
    from shapely.geometry import Polygon
    from app.routing.planner import (
        Suggestion, _honest_labels, LABEL_FRIENDS, LABEL_NEW, LABEL_CLOSEST, LABEL_OTHER,
    )

    def sug(new, stolen, dist, label):
        return Suggestion(
            route=[(0.0, 0.0), (0.0, 0.001), (0.0, 0.0)], distance_m=dist,
            enclosed=Polygon([(0, 0), (0, 1), (1, 1)]), new_area_sq_m=new,
            stolen_area_sq_m=stolen, stolen_by_user={}, already_mine_sq_m=0.0,
            gain_sq_m=new + stolen, score=new + stolen, label=label, reason="",
        )

    # The real 3 km case: the friends' pick also has the most new land, so the
    # second pick must not claim "Most new land".
    out = _honest_labels([
        sug(296_000, 17_000, 3350, LABEL_FRIENDS),
        sug(104_000, 13_000, 2640, LABEL_NEW),
        sug(99_000, 5_000, 2770, LABEL_CLOSEST),
    ], target=3000)
    assert [g.label for g in out] == [LABEL_FRIENDS, LABEL_OTHER, LABEL_CLOSEST]

    # When each leads on something, each keeps a true label.
    out = _honest_labels([
        sug(50_000, 20_000, 3600, LABEL_FRIENDS),
        sug(90_000, 0, 3500, LABEL_NEW),
        sug(30_000, 0, 3020, LABEL_CLOSEST),
    ], target=3000)
    assert [g.label for g in out] == [LABEL_FRIENDS, LABEL_NEW, LABEL_CLOSEST]
