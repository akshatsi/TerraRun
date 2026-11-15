"""Land enclosed by a runner's territory (app/gps/enclosure.py). No database needed.

Synthetic coordinates only: a local metre grid around lat 10.0, lng 20.0.
Strips are built like route strips: 3 m each side of a line, flat ends.
"""
import math
import random
import time

import numpy as np
import pytest
import shapely
from pyproj import CRS, Geod, Transformer
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from app.gps.enclosure import EnclosureConfig, enclosed_by

LAT0, LNG0 = 10.0, 20.0
HALF_W = 3.0
_GEOD = Geod(ellps="WGS84")
_CRS = CRS.from_proj4(f"+proj=aeqd +lat_0={LAT0} +lon_0={LNG0} +datum=WGS84 +units=m +no_defs")
_INV = Transformer.from_crs(_CRS, CRS.from_epsg(4326), always_xy=True)
_FWD = Transformer.from_crs(CRS.from_epsg(4326), _CRS, always_xy=True)


def _tr(tr, geom):
    def f(c):
        x, y = tr.transform(c[:, 0], c[:, 1])
        return np.column_stack([x, y])
    return shapely.transform(geom, f)


def to_ll(geom_xy):
    return _tr(_INV, geom_xy)


def to_xy(geom_ll):
    return _tr(_FWD, geom_ll)


def strip(*corners):
    """A route strip (metres) along a polyline given in local metres."""
    return LineString(corners).buffer(HALF_W, cap_style="flat", join_style="round")


def territory(*parts_xy):
    return to_ll(unary_union(parts_xy))


def area(geom):
    if geom is None:
        return 0.0
    return sum(abs(_GEOD.geometry_area_perimeter(orient(p, 1.0))[0])
               for p in getattr(geom, "geoms", [geom]))


def contains_xy(geom, x, y):
    return geom is not None and geom.contains(to_ll(Point(x, y)))


def check(result, terr):
    """Valid polygonal NEW land, disjoint from the territory, inside its hull."""
    if result is None:
        return
    assert isinstance(result, (Polygon, MultiPolygon))
    assert result.is_valid and not result.is_empty
    assert area(result.intersection(terr)) < 1.0
    assert area(result.difference(terr.convex_hull)) < 1.0


# The rectangle's four sides as strips from four separate runs (150 x 100 m between centrelines).
BOTTOM = strip((0, 0), (150, 0))
RIGHT = strip((150, 0), (150, 100))
TOP = strip((150, 100), (0, 100))
LEFT = strip((0, 100), (0, 0))
INNER = (150 - 2 * HALF_W) * (100 - 2 * HALF_W)  # land strictly inside the strips


def test_rectangle_of_four_runs_is_filled():
    terr = territory(BOTTOM, RIGHT, TOP, LEFT)
    got = enclosed_by(terr)
    check(got, terr)
    assert got is not None
    assert area(got) == pytest.approx(INNER, rel=0.02)
    # With the strips it covers the whole 150 x 100 m rectangle.
    assert area(unary_union([got, terr])) >= 0.98 * 150 * 100
    assert contains_xy(got, 75, 50) and contains_xy(got, 10, 10) and contains_xy(got, 140, 90)
    assert not contains_xy(got, 75, -10) and not contains_xy(got, 160, 50)


def test_rectangle_with_15_m_corner_gap_is_filled_without_bulk():
    top = strip((135, 100), (0, 100))  # stopped 15 m short of the corner
    terr = territory(BOTTOM, RIGHT, top, LEFT)
    got = enclosed_by(terr)
    check(got, terr)
    assert got is not None
    assert area(got) == pytest.approx(INNER, rel=0.03)
    # The bridge does not spill out of the gap's mouth.
    assert not contains_xy(got, 141, 102) and not contains_xy(got, 141, 105)


def test_rectangle_with_60_m_gap_is_not_filled():
    top = strip((90, 100), (0, 100))
    terr = territory(BOTTOM, RIGHT, top, LEFT)
    assert enclosed_by(terr) is None


def test_parallel_strips_15_m_apart_are_not_joined():
    terr = territory(strip((0, 0), (300, 0)), strip((0, 15), (300, 15)))
    assert enclosed_by(terr) is None


def test_extra_parallel_pavement_does_not_add_the_sliver():
    outer = strip((0, -15), (150, -15))  # the other pavement, 15 m outside the bottom side
    terr = territory(BOTTOM, RIGHT, TOP, LEFT, outer)
    got = enclosed_by(terr)
    check(got, terr)
    assert area(got) == pytest.approx(INNER, rel=0.02)
    assert not contains_xy(got, 75, -7.5)


@pytest.mark.parametrize("parts", [
    (BOTTOM, LEFT),                                         # L
    (LEFT, BOTTOM, RIGHT),                                  # U, open at the top
    (strip((0, 100), (0, 0), (150, 0), (150, 100)),),      # U in one run
])
def test_open_shapes_fill_nothing(parts):
    assert enclosed_by(territory(*parts)) is None


def test_existing_hole_of_2000_m2_is_returned():
    hole = box(80, 80, 130, 120)  # 50 x 40 m
    terr = to_ll(box(0, 0, 200, 200).difference(hole))
    got = enclosed_by(terr)
    check(got, terr)
    assert area(got) == pytest.approx(2000.0, rel=0.01)


def test_small_hole_of_100_m2_is_not_returned():
    terr = to_ll(box(0, 0, 200, 200).difference(box(95, 95, 105, 105)))
    assert enclosed_by(terr) is None


def test_thin_enclosed_corridor_is_not_filled():
    # Centrelines 16 m apart leave 10 m between strip edges, closed at both ends.
    terr = territory(strip((0, 0), (200, 0)), strip((0, 16), (200, 16)),
                     strip((0, 0), (0, 16)), strip((200, 0), (200, 16)))
    assert enclosed_by(terr) is None


def test_good_face_kept_when_a_sliver_is_dropped():
    # The rectangle plus a 10 m corridor walled off alongside it.
    corridor = (strip((0, -16), (150, -16)), strip((0, -16), (0, 0)), strip((150, -16), (150, 0)))
    terr = territory(BOTTOM, RIGHT, TOP, LEFT, *corridor)
    got = enclosed_by(terr)
    check(got, terr)
    assert area(got) == pytest.approx(INNER, rel=0.02)
    assert not contains_xy(got, 75, -8)


def test_min_area_and_width_are_configurable():
    terr = to_ll(box(0, 0, 200, 200).difference(box(95, 95, 105, 105)))
    got = enclosed_by(terr, EnclosureConfig(min_area_sq_m=50, min_width_m=5))
    assert area(got) == pytest.approx(100.0, rel=0.02)


def test_zero_gap_bridges_nothing():
    top = strip((135, 100), (0, 100))
    assert enclosed_by(territory(BOTTOM, RIGHT, top, LEFT), EnclosureConfig(gap_m=0)) is None


@pytest.mark.parametrize("geom", [
    None,
    Polygon(),
    MultiPolygon(),
    to_ll(box(0, 0, 5, 5)),
    to_ll(LineString([(0, 0), (100, 0)])),
    to_ll(strip((0, 0), (300, 0))),
])
def test_nothing_to_fill(geom):
    assert enclosed_by(geom) is None


def test_invalid_input_is_repaired():
    # A bow-tie ring around the rectangle: invalid as given.
    outer = to_ll(Polygon([(-10, -10), (160, 110), (160, -10), (-10, 110)]))
    assert not outer.is_valid
    enclosed_by(outer)  # must not raise
    # A valid territory given as a GeometryCollection with a stray line.
    terr = territory(BOTTOM, RIGHT, TOP, LEFT)
    coll = shapely.GeometryCollection([terr, to_ll(LineString([(0, 0), (400, 400)]))])
    assert area(enclosed_by(coll)) == pytest.approx(INNER, rel=0.02)


def test_multipolygon_input():
    terr = territory(BOTTOM, RIGHT, TOP, LEFT, strip((500, 0), (600, 0)))
    assert isinstance(terr, MultiPolygon)
    got = enclosed_by(terr)
    check(got, terr)
    assert area(got) == pytest.approx(INNER, rel=0.02)


def _wobbly(rng, a, b, step=2.0, sigma=1.0):
    n = max(2, int(math.dist(a, b) / step))
    pts = [(a[0] + (b[0] - a[0]) * k / n + rng.gauss(0, sigma),
            a[1] + (b[1] - a[1]) * k / n + rng.gauss(0, sigma)) for k in range(n + 1)]
    return LineString(pts).buffer(HALF_W, cap_style="flat", join_style="round")


def test_grid_of_runs_is_fast_and_fills_every_block():
    rng = random.Random(7)
    pitch, n = 120.0, 6  # 6 x 6 lines -> 5 x 5 blocks
    parts = []
    for i in range(n):
        for j in range(n - 1):
            # Each block side is its own run, stopping 5-10 m short of the junction.
            s0, s1 = rng.uniform(5, 10), rng.uniform(5, 10)
            parts.append(_wobbly(rng, (i * pitch, j * pitch + s0), (i * pitch, (j + 1) * pitch - s1)))
            parts.append(_wobbly(rng, (j * pitch + s0, i * pitch), ((j + 1) * pitch - s1, i * pitch)))
    terr = territory(*parts)
    assert len(getattr(terr, "geoms", [terr])) >= 50
    assert shapely.get_num_coordinates(terr) > 5000
    enclosed_by(terr)  # warm up the projection machinery
    t0 = time.perf_counter()
    got = enclosed_by(terr)
    elapsed = time.perf_counter() - t0
    check(got, terr)
    assert elapsed < 0.5, f"took {elapsed:.2f} s"
    assert len(got.geoms) == 25
    block = (pitch - 2 * HALF_W) ** 2
    assert area(got) == pytest.approx(25 * block, rel=0.05)
