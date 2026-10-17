"""Territory shape for one run (rules v2). Pure Python; no database.

A run earns one of three shapes (see docs/gps-accuracy.md section 4):

* ``loop``  -- the runner came back to within ``closure_radius_m`` of the start.
  The award is only the area the path encloses, with no corridor around it.
* ``route`` -- any other run. The award is a strip ``route_half_width_m`` each
  side of each accepted segment, with flat ends, never across a gap.
* ``none``  -- fewer than 2 accepted fixes, or nothing left after the rules.

Quality and minimum-distance rules belong to the database layer, not here.

Design notes
------------
Projection.  All buffering, simplifying and noding happens in metres, in an
azimuthal equidistant projection (``+proj=aeqd``, WGS-84) centred on the run's
bounding-box centre and built per call. Within 10 km of the centre its scale
error is below 1e-6, so a 3 m buffer is 3 m on the ground. We never buffer in
degrees (a degree of longitude is ~15% shorter than one of latitude at 27 N)
or in EPSG:3857 (scale 1/cos(lat), ~12% too large here). The result goes back
to WGS-84 lon/lat for storage.

Area.  ``area_sq_m`` is geodesic: ``pyproj.Geod(ellps="WGS84")`` on the WGS-84
result, each polygon oriented first so parts never cancel, the same quantity
PostGIS reports for ``ST_Area(geom::geography)``.

Loop test.  ``closure_distance_m`` is the geodesic distance from the first fix
of the first segment to the last fix of the last segment. A loop also needs a
path (segment lengths plus ``uncertain_distance_m``) of at least
``min_loop_perimeter_m``, and gaps at most ``max_gap_fraction_for_loop`` of it.
The boundaries are inclusive, with 1 cm of slack for float round-off.

Enclosed area.  The segments are joined in order (a straight line across each
gap, allowed only by the gap rule) and closed back to the first fix. The ring
is simplified (Douglas-Peucker, ``simplify_tolerance_m``) to drop jitter, then
noded with ``unary_union`` so every self-crossing becomes a vertex, and
polygonized. The award is the union of all bounded faces: everything the path
walls off from the outside. This handles the hard cases without any winding
or orientation logic, which signed area gets wrong:

* figure-8: two faces, one each side of the crossing; both count (a signed
  shoelace sum would cancel them to ~0);
* lollipop: an out-and-back stick is a dangle after noding, encloses no face
  and adds nothing;
* the same loop run twice: the faces between the two laps are inside the
  outer boundary, so the union is the loop counted once;
* out-and-back on one street: the path walls off nothing (or thin slivers).

Real GPS never retraces a street exactly, so the out and back legs of a stick
leave thin sliver faces between them. These are removed with a morphological
opening: shrink by ``route_half_width_m``, grow back by the same, intersect
with the faces. That deletes any part narrower than the route strip (6 m) and
leaves wider land unchanged, apart from tiny jags along the edge. A region
narrower than the road strip cannot be told apart from noise on a retraced
road, so it is not enclosed land. Mitre joins keep the corners of real loops
square; the final intersection guarantees the opening never adds land. If what
is left is under ``min_loop_area_sq_m`` the run is scored as a route, and
``reason`` says so.

Route strip.  Each segment (consecutive duplicates removed, simplified with the
same tolerance) is buffered on its own with flat caps, then the pieces are
unioned, so no strip crosses a gap. Joins are round, not mitred: a round join
makes the strip exactly the set of points within ``route_half_width_m`` of the
path (apart from the flat ends), while a mitre on a sharp GPS zig-zag or
hairpin throws a spike out to ``mitre_limit`` x 3 m over land the runner never
came near. At a 90 degree corner the round join gives up only
(1 - pi/4) x 3^2 = 1.9 m2 against a mitre.

Output.  A valid shapely Polygon or MultiPolygon in WGS-84 (x=lng, y=lat),
made valid again after the transform, with only polygonal, non-empty parts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import shapely
from pyproj import CRS, Geod, Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

from .geodesy import valid_coordinate

_GEOD = Geod(ellps="WGS84")
_EPS_M = 0.01  # slack for inclusive boundaries, and the duplicate-point distance
_MIN_PART_SQ_M = 0.01  # polygon parts smaller than this are numerical dust


@dataclass
class ShapeConfig:
    closure_radius_m: float = 20.0
    min_loop_perimeter_m: float = 100.0
    min_loop_area_sq_m: float = 200.0
    route_half_width_m: float = 3.0
    max_gap_fraction_for_loop: float = 0.1
    simplify_tolerance_m: float = 1.5


@dataclass
class TerritoryShape:
    kind: str  # "loop" | "route" | "none"
    geometry: Optional[BaseGeometry]  # Polygon/MultiPolygon in WGS-84; None for "none"
    area_sq_m: float
    closure_distance_m: Optional[float]
    reason: str


# ---------------------------------------------------------------- helpers


def _fmt_len(m: float) -> str:
    return f"{m / 1000:.1f} km" if m >= 1000 else f"{m:,.0f} m"


def _fmt_w(m: float) -> str:
    return f"{m:g} m"


def _geod_dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    """a, b are (lat, lng)."""
    return float(_GEOD.inv(a[1], a[0], b[1], b[0])[2])


def _geod_len(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    return float(_GEOD.line_length(lngs, lats))


def _polygonal(geom: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
    """Polygonal parts of geom as a Polygon or MultiPolygon, or None."""
    if geom is None or geom.is_empty:
        return None
    polys: list[Polygon] = []
    stack = [geom]
    while stack:
        g = stack.pop()
        if g.is_empty:
            continue
        if isinstance(g, Polygon):
            polys.append(g)
        elif hasattr(g, "geoms"):
            stack.extend(g.geoms)
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def _clean(geom: Optional[BaseGeometry], min_part: float) -> Optional[BaseGeometry]:
    """Valid, polygonal, no part below min_part (in the geometry's own units)."""
    geom = _polygonal(geom)
    if geom is None:
        return None
    if not geom.is_valid:
        geom = _polygonal(shapely.make_valid(geom))
        if geom is None:
            return None
    parts = [p for p in getattr(geom, "geoms", [geom]) if p.area > min_part]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


def _geodesic_area(geom: BaseGeometry) -> float:
    total = 0.0
    for p in getattr(geom, "geoms", [geom]):
        area, _ = _GEOD.geometry_area_perimeter(orient(p, sign=1.0))
        total += abs(area)
    return total


class _Frame:
    """Local azimuthal equidistant frame in metres, centred on the run."""

    def __init__(self, lat0: float, lng0: float):
        crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={lat0!r} +lon_0={lng0!r} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )
        wgs = CRS.from_epsg(4326)
        self._fwd = Transformer.from_crs(wgs, crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, wgs, always_xy=True)

    def to_xy(self, pts: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        if not pts:
            return []
        xs, ys = self._fwd.transform([p[1] for p in pts], [p[0] for p in pts])
        return list(zip((float(x) for x in xs), (float(y) for y in ys)))

    def to_lnglat(self, geom: BaseGeometry) -> BaseGeometry:
        def inv(coords):
            lng, lat = self._inv.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([lng, lat])

        return shapely.transform(geom, inv)


def _dedupe(xy: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in xy:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > _EPS_M:
            out.append(p)
    return out


# ---------------------------------------------------------------- shapes


def _route_strip(segs_xy: list[list[tuple[float, float]]], cfg: ShapeConfig) -> Optional[BaseGeometry]:
    pieces = []
    for xy in segs_xy:
        if len(xy) < 2:
            continue
        line = LineString(xy)
        if cfg.simplify_tolerance_m > 0:
            line = line.simplify(cfg.simplify_tolerance_m, preserve_topology=False)
        if line.length <= _EPS_M:
            continue
        pieces.append(
            line.buffer(cfg.route_half_width_m, quad_segs=8, cap_style="flat", join_style="round")
        )
    if not pieces:
        return None
    return _clean(unary_union(pieces), _MIN_PART_SQ_M)


def _enclosed(segs_xy: list[list[tuple[float, float]]], cfg: ShapeConfig) -> Optional[BaseGeometry]:
    ring = _dedupe([p for xy in segs_xy for p in xy])
    if len(ring) < 3:
        return None
    ring.append(ring[0])
    line = LineString(ring)
    if cfg.simplify_tolerance_m > 0:
        line = line.simplify(cfg.simplify_tolerance_m, preserve_topology=True)
    noded = unary_union(line)
    faces = [f for f in polygonize(noded) if not f.is_empty and f.area > 0]
    if not faces:
        return None
    filled = _clean(unary_union(faces), _MIN_PART_SQ_M)
    if filled is None:
        return None
    e = cfg.route_half_width_m
    if e > 0:
        opened = filled.buffer(-e, join_style="mitre", mitre_limit=5.0)
        if opened.is_empty:
            return None
        opened = opened.buffer(e, join_style="mitre", mitre_limit=5.0)
        filled = _clean(opened.intersection(filled), _MIN_PART_SQ_M)
    return filled


def _finish(kind: str, geom_xy: Optional[BaseGeometry], frame: _Frame, closure: Optional[float],
            reason: str) -> TerritoryShape:
    if geom_xy is None:
        return TerritoryShape("none", None, 0.0, closure, reason)
    geom = _clean(frame.to_lnglat(geom_xy), 0.0)
    if geom is None:
        return TerritoryShape("none", None, 0.0, closure, reason)
    return TerritoryShape(kind, geom, _geodesic_area(geom), closure, reason)


def build_territory_shape(
    segments: list[list[tuple[float, float]]],
    uncertain_distance_m: float = 0.0,
    config: ShapeConfig = ShapeConfig(),
) -> TerritoryShape:
    """Decide the territory a run earns.

    segments: accepted fixes per segment, as (lat, lng), in order.
    uncertain_distance_m: straight-line distance across gaps, from the engine.
    """
    cfg = config
    segs = [
        [(float(la), float(ln)) for la, ln in seg if valid_coordinate(la, ln)]
        for seg in (segments or [])
    ]
    segs = [s for s in segs if s]
    n_fixes = sum(len(s) for s in segs)
    if n_fixes < 2:
        return TerritoryShape("none", None, 0.0, None, "Fewer than 2 accepted fixes")

    first, last = segs[0][0], segs[-1][-1]
    closure = _geod_dist(first, last)
    seg_len = sum(_geod_len(s) for s in segs)
    gap = max(0.0, float(uncertain_distance_m or 0.0))
    path = seg_len + gap

    all_pts = [p for s in segs for p in s]
    lats = [p[0] for p in all_pts]
    lngs = [p[1] for p in all_pts]
    frame = _Frame((min(lats) + max(lats)) / 2, (min(lngs) + max(lngs)) / 2)
    segs_xy = [_dedupe(frame.to_xy(s)) for s in segs]

    # Loop test.
    why_not = None
    if closure > cfg.closure_radius_m + _EPS_M:
        why_not = f"ended {closure:,.0f} m from start (loop needs {cfg.closure_radius_m:g} m or less)"
    elif path < cfg.min_loop_perimeter_m - _EPS_M:
        why_not = f"path {_fmt_len(path)} is under the {cfg.min_loop_perimeter_m:g} m loop minimum"
    elif gap > cfg.max_gap_fraction_for_loop * path + _EPS_M:
        why_not = (f"gaps are {gap / path:.0%} of the loop "
                   f"(at most {cfg.max_gap_fraction_for_loop:.0%} allowed)")
    else:
        area_xy = _enclosed(segs_xy, cfg)
        if area_xy is not None:
            shape = _finish("loop", area_xy, frame, closure, "")
            if shape.kind == "loop" and shape.area_sq_m >= cfg.min_loop_area_sq_m:
                shape.reason = f"Loop closed {closure:,.0f} m from start; {shape.area_sq_m:,.0f} m² enclosed"
                return shape
            enclosed = shape.area_sq_m
        else:
            enclosed = 0.0
        why_not = (f"loop closed {closure:,.0f} m from start but encloses only {enclosed:,.0f} m² "
                   f"(under {cfg.min_loop_area_sq_m:g})")

    strip = _route_strip(segs_xy, cfg)
    if strip is None:
        return TerritoryShape("none", None, 0.0, closure, "No movement: nothing to award")
    reason = f"Route: {_fmt_w(cfg.route_half_width_m)} each side of {_fmt_len(seg_len)}; {why_not}"
    shape = _finish("route", strip, frame, closure, reason)
    if shape.kind == "none":
        shape.reason = "No movement: nothing to award"
    return shape
