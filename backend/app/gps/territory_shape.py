"""Territory shape for one run (rules v2). Pure Python; no database.

A run earns one of three shapes (see docs/gps-accuracy.md section 4):

* ``loop``  -- the path encloses at least ``min_loop_area_sq_m``. The award is
  the enclosed area plus a route strip along the tails and spurs outside it;
  the loop's own edge gets no corridor.
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

Start-to-end join.  ``closure_distance_m`` is the geodesic distance from the
first fix of the first segment to the last fix of the last segment. The path
is closed with a straight line from the last fix back to the first when:
closure <= ``closure_radius_m`` (200 m); path (segment lengths plus
``uncertain_distance_m``) >= ``min_loop_perimeter_m``; gaps <=
``max_gap_fraction_for_loop`` of the path; and closure <=
``max_closure_fraction`` (25%) of the path. The last rule stops a long arc
claiming the land under its chord: with a 25% limit the runner walked at least
80% of the ring. Only when the join is made are gaps bridged with straight
lines; otherwise each segment stays a separate line. Boundaries are inclusive,
with 1 cm of slack for float round-off.

Enclosed area.  The walked lines are simplified (Douglas-Peucker,
``simplify_tolerance_m``, topology kept), noded with ``unary_union`` so every
self-crossing becomes a vertex, and polygonized. Every bounded face counts, so
a loop anywhere in the run (before or after a tail, or where the path crosses
itself) earns its area. No winding or orientation logic, which signed area
gets wrong:

* figure-8: two faces, one each side of the crossing; both count (a signed
  shoelace sum would cancel them to ~0);
* lollipop: an out-and-back stick is a dangle after noding, encloses no face
  and adds nothing;
* the same loop run twice: the faces between the two laps are inside the
  outer boundary, so the union is the loop counted once;
* out-and-back on one street: the path walls off nothing (or thin slivers).

Near-closures.  GPS rarely crosses its own track exactly: a runner who comes
back to a corner draws a line that stops 5-10 m short of it. So for each
vertex we find the nearest point on any other segment within ``self_snap_m``
(15 m) whose along-path distance from the vertex is at least
``self_snap_min_separation_m`` (100 m), and add a connector from the vertex
to it (to the exact vertex if the nearest point is a segment end, else 0.5 m
past the segment so that noding sees a crossing). Vertex-to-segment checks in
both directions find every close approach, since two segments that do not
cross are closest at an endpoint of one of them. 15 m is about twice the
10 m accuracy of a good fix: two passes over one spot rarely differ by more.
The separation rule keeps a path from closing on its own neighbouring fixes;
100 m matches the loop perimeter minimum, and a smooth path cannot come back
within 15 m of a point 100 m behind it without turning round.

Guessed edges.  The join and the connectors are guesses, not walked path. A
face that needs one of them counts only if it holds a disc of radius
``self_snap_m``, i.e. it is wider than 30 m somewhere. Two legs of an
out-and-back within 15 m of each other (two pavements of one road) make faces
no wider than the gap, which this drops; a real loop closed by a join or a
near-miss is far wider. Faces formed by walked lines alone are always kept.

Slivers.  Real GPS never retraces a street exactly, so the out and back legs
of a stick leave thin faces between them. These are removed with a
morphological opening: shrink by ``route_half_width_m``, grow back by the
same, intersect with the faces. That deletes any part narrower than the route
strip (6 m) and leaves wider land unchanged, apart from tiny jags along the
edge. Mitre joins keep the corners of real loops square; the final
intersection guarantees the opening never adds land. Each remaining part must
have a perimeter of at least ``min_loop_perimeter_m``. If the total is under
``min_loop_area_sq_m`` the run is scored as a route, and ``reason`` says so.

Tails.  The walked path minus the enclosed area, keeping only pieces that
reach more than ``route_half_width_m + simplify_tolerance_m`` from it (closer
pieces are the loop's own edge, moved by simplifying or by the opening). Each
kept piece starts on the area's edge and is buffered like the route strip, so
the award stays one connected shape. The join and connectors earn no strip.

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
    closure_radius_m: float = 200.0  # join end to start when this close
    max_closure_fraction: float = 0.25  # ... and the join is at most this share of the path
    min_loop_perimeter_m: float = 100.0
    min_loop_area_sq_m: float = 200.0
    route_half_width_m: float = 3.0
    max_gap_fraction_for_loop: float = 0.1
    simplify_tolerance_m: float = 1.5
    self_snap_m: float = 15.0  # a return this close to an earlier part of the path closes it
    self_snap_min_separation_m: float = 100.0  # ... if that part is this far back along the path


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


def _strip(lines: list[LineString], cfg: ShapeConfig) -> Optional[BaseGeometry]:
    """route_half_width_m each side of each line, flat ends, round joins."""
    pieces = []
    for line in lines:
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


def _route_strip(segs_xy: list[list[tuple[float, float]]], cfg: ShapeConfig) -> Optional[BaseGeometry]:
    return _strip([LineString(xy) for xy in segs_xy if len(xy) >= 2], cfg)


def _tails(segs_xy: list[list[tuple[float, float]]], area: BaseGeometry,
           cfg: ShapeConfig) -> list[LineString]:
    """Walked path outside the enclosed area: tails and spurs.

    A piece that stays within route_half_width_m + simplify_tolerance_m of the
    area is the loop's own edge, moved by simplifying or by the sliver opening,
    and is dropped. Kept pieces start on the area's edge, so their strips join it.
    """
    near = area.buffer(cfg.route_half_width_m + cfg.simplify_tolerance_m)
    out: list[LineString] = []
    for xy in segs_xy:
        if len(xy) < 2:
            continue
        stack = [LineString(xy).difference(area)]
        while stack:
            g = stack.pop()
            if g.is_empty:
                continue
            if isinstance(g, LineString):
                if g.length > _EPS_M and not near.contains(g):
                    out.append(g)
            elif hasattr(g, "geoms"):
                stack.extend(g.geoms)
    return out


def _linework(segs_xy: list[list[tuple[float, float]]], bridge: bool, cfg: ShapeConfig) -> list[LineString]:
    """The walked path as simplified lines: one chain across gaps if bridge, else one per segment."""
    chains = [_dedupe([p for xy in segs_xy for p in xy])] if bridge else segs_xy
    lines = []
    for xy in chains:
        if len(xy) < 2:
            continue
        line = LineString(xy)
        if cfg.simplify_tolerance_m > 0:
            line = line.simplify(cfg.simplify_tolerance_m, preserve_topology=True)
        if line.length > _EPS_M:
            lines.append(line)
    return lines


def _snap_connectors(lines: list[LineString], cfg: ShapeConfig) -> list[LineString]:
    """Short connectors where the path comes back near an earlier part of itself.

    For each vertex, the nearest point on any path segment within self_snap_m
    whose along-path distance from the vertex is at least
    self_snap_min_separation_m. Checking vertices against segments in both
    directions finds every close approach: two segments that do not cross are
    closest at an endpoint of one of them.
    """
    r, sep = cfg.self_snap_m, cfg.self_snap_min_separation_m
    if r <= 0 or not lines:
        return []
    verts, segs = [], []
    s, prev_end = 0.0, None
    for line in lines:
        c = np.asarray(line.coords, dtype=float)[:, :2]
        if prev_end is not None:
            s += float(np.hypot(*(c[0] - prev_end)))  # along-path distance counts the gap
        cum = s + np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(c, axis=0).T))])
        verts.append(np.column_stack([c, cum]))
        segs.append(np.column_stack([c[:-1], c[1:], cum[:-1]]))
        s, prev_end = float(cum[-1]), c[-1]
    V, S = np.vstack(verts), np.vstack(segs)
    tree = shapely.STRtree(shapely.linestrings(S[:, :4].reshape(-1, 2, 2)))
    vi, si = tree.query(shapely.points(V[:, :2]), predicate="dwithin", distance=r)
    if len(vi) == 0:
        return []
    P, A, B = V[vi, :2], S[si, 0:2], S[si, 2:4]
    AB = B - A
    L2 = (AB ** 2).sum(axis=1)
    t = np.clip(np.divide(((P - A) * AB).sum(axis=1), L2, out=np.zeros_like(L2), where=L2 > 0), 0.0, 1.0)
    Q = A + t[:, None] * AB
    dist = np.hypot(*(Q - P).T)
    along = np.abs(S[si, 4] + t * np.sqrt(L2) - V[vi, 2])
    ok = (along >= sep - _EPS_M) & (dist <= r + _EPS_M) & (dist > 1e-6)
    best: dict[int, int] = {}
    for k in np.flatnonzero(ok):
        v = int(vi[k])
        if v not in best or dist[k] < dist[best[v]]:
            best[v] = int(k)
    out = []
    for v, k in best.items():
        p = tuple(V[v, :2])
        if t[k] <= 1e-9:
            q = tuple(A[k])  # exact vertex, so noding joins them
        elif t[k] >= 1 - 1e-9:
            q = tuple(B[k])
        else:
            u = (Q[k] - P[k]) / dist[k]
            q = tuple(Q[k] + 0.5 * u)  # run 0.5 m past the segment so it is crossed, not just touched
        out.append(LineString([p, q]))
    return out


def _faces(lines: list[LineString]) -> list[Polygon]:
    return [f for f in polygonize(unary_union(lines)) if not f.is_empty and f.area > 0]


def _enclosed(lines: list[LineString], closing: list[LineString],
              cfg: ShapeConfig) -> tuple[Optional[BaseGeometry], bool]:
    """Enclosed area in metres, and whether added lines (join, snaps) supplied most of it."""
    if not lines:
        return None, False
    real = _faces(lines)
    added = closing + _snap_connectors(lines, cfg)
    guessed: list[Polygon] = []
    if added:
        r = cfg.self_snap_m
        for f in _faces(lines + added):
            # A face that needs an added line must hold a disc of radius self_snap_m.
            if r <= 0 or (f.area >= math.pi * r * r and not f.buffer(-r).is_empty):
                guessed.append(f)
    if not real and not guessed:
        return None, False
    filled = _clean(unary_union(real + guessed), _MIN_PART_SQ_M)
    if filled is None:
        return None, False
    e = cfg.route_half_width_m
    if e > 0:
        opened = filled.buffer(-e, join_style="mitre", mitre_limit=5.0)
        if opened.is_empty:
            return None, False
        opened = opened.buffer(e, join_style="mitre", mitre_limit=5.0)
        filled = _clean(opened.intersection(filled), _MIN_PART_SQ_M)
        if filled is None:
            return None, False
    # Each enclosed part is a loop in its own right and needs the loop perimeter.
    parts = [p for p in getattr(filled, "geoms", [filled])
             if p.exterior.length >= cfg.min_loop_perimeter_m - _EPS_M]
    if not parts:
        return None, False
    filled = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    by_added = False
    if guessed:
        gain = unary_union(guessed)
        if real:
            gain = gain.difference(unary_union(real))
        by_added = gain.intersection(filled).area >= 0.5 * filled.area
    return filled, by_added


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

    # Start-to-end join: also the only case that bridges gaps.
    why_no_join = None
    if closure > cfg.closure_radius_m + _EPS_M:
        why_no_join = f"ended {closure:,.0f} m from start (a loop needs {cfg.closure_radius_m:g} m or less)"
    elif path < cfg.min_loop_perimeter_m - _EPS_M:
        why_no_join = f"path {_fmt_len(path)} is under the {cfg.min_loop_perimeter_m:g} m loop minimum"
    elif gap > cfg.max_gap_fraction_for_loop * path + _EPS_M:
        why_no_join = (f"gaps are {gap / path:.0%} of the loop "
                       f"(at most {cfg.max_gap_fraction_for_loop:.0%} allowed)")
    elif closure > cfg.max_closure_fraction * path + _EPS_M:
        why_no_join = (f"the {closure:,.0f} m from end back to start is over "
                       f"{cfg.max_closure_fraction:.0%} of the {_fmt_len(path)} path")
    joined = why_no_join is None

    lines = _linework(segs_xy, joined, cfg)
    closing = []
    if joined and lines:
        a, b = lines[-1].coords[-1], lines[0].coords[0]
        if a != b:
            closing = [LineString([a, b])]

    area_xy, by_added = _enclosed(lines, closing, cfg)
    enclosed = 0.0
    if area_xy is not None:
        area_ll = _clean(frame.to_lnglat(area_xy), 0.0)
        enclosed = _geodesic_area(area_ll) if area_ll is not None else 0.0
    if enclosed >= cfg.min_loop_area_sq_m:
        if joined and (by_added or not closing):
            head = f"Loop closed {closure:,.0f} m from start"
        elif not by_added:
            head = "Path crossed itself"
        else:
            head = f"Path came back within {cfg.self_snap_m:g} m of itself"
        reason = f"{head}; {enclosed:,.0f} m² enclosed"
        tails = _tails(segs_xy, area_xy, cfg)
        tail_len = sum(t.length for t in tails)
        if tail_len >= 10.0:
            reason += f" + {_fmt_len(tail_len)} of route"
        tail_strip = _strip(tails, cfg)
        geom = area_xy if tail_strip is None else _clean(unary_union([area_xy, tail_strip]), _MIN_PART_SQ_M)
        shape = _finish("loop", geom, frame, closure, reason)
        if shape.kind == "loop":
            return shape

    if joined:
        why_not = (f"loop closed {closure:,.0f} m from start but encloses only {enclosed:,.0f} m² "
                   f"(under {cfg.min_loop_area_sq_m:g})")
    else:
        why_not = why_no_join
        if enclosed >= 1.0:
            why_not += f"; path encloses only {enclosed:,.0f} m² (under {cfg.min_loop_area_sq_m:g})"
    strip = _route_strip(segs_xy, cfg)
    if strip is None:
        return TerritoryShape("none", None, 0.0, closure, "No movement: nothing to award")
    reason = f"Route: {_fmt_w(cfg.route_half_width_m)} each side of {_fmt_len(seg_len)}; {why_not}"
    shape = _finish("route", strip, frame, closure, reason)
    if shape.kind == "none":
        shape.reason = "No movement: nothing to award"
    return shape
