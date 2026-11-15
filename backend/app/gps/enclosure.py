"""Land enclosed by a runner's territory across runs (rules v4). Pure Python; no database.

See docs/gps-accuracy.md section 7. Territory builds up run by run: loops earn
their inside, routes earn a 3 m strip each side of the road. When the strips
from several runs wall off an area, that area becomes the runner's too, like a
loop closed across runs. ``enclosed_by`` finds that area.

Design notes
------------
Projection.  Work is done in metres, in an azimuthal equidistant projection
(``+proj=aeqd``, WGS-84) centred on the territory's bounding box, built per
call, the same frame ``territory_shape`` uses. The result goes back to WGS-84
lon/lat.

True holes.  An interior ring of a territory polygon is land the territory
already walls off with no gap at all. Each one (minus any territory that sits
inside it) is a candidate as it is.

Gaps.  Strips from different runs rarely meet exactly: GPS error, or a run
that stopped a few metres short of the street it was heading for, leaves a gap.
Gaps up to ``gap_m`` are bridged with a morphological closing, with
``g = gap_m / 2``:

1. ``D = territory.buffer(g)``. Any two edges up to ``gap_m`` apart now touch.
   A hole of ``D`` is land walled off once the gaps are bridged; nothing else
   is. Two parallel strips 15 m apart merge into one wide band with no hole;
   the bay beside an L or a U is open to the outside and has no hole either.
   So the holes of ``D`` decide WHETHER land is enclosed, and they are the only
   seeds used.
2. ``E = fill_holes(D).buffer(-g)`` is the closing of the territory with its
   holes filled. It reaches out to the territory edge everywhere inside an
   enclosed face (so the face keeps its full size and square corners), bridges
   each gap roughly along the line between the strip ends, and adds nothing
   past a convex outer edge. A closing never leaves the convex hull.
3. The candidates are the connected parts of ``E - territory`` that contain a
   hole of ``D``. That drops the closing's bulk elsewhere: the space filled
   between two parallel strips, or in an open bay, is a separate part with no
   hole in it.
4. A morphological opening by ``g`` (shrink by ``g``, grow back with mitred
   corners, keep only what was there) trims what the closing glued onto a face:
   the few metres of bridge in a gap's mouth, or a strip-wide sliver between
   two parallel pavements that opens into the face. It removes any arm of the
   face narrower than ``gap_m``, which only matters for faces that needed a
   bridge; true holes keep their full shape.

Size.  Each part of the result must cover at least ``min_area_sq_m`` and be
wider than ``min_width_m`` somewhere: it must hold a disc of radius
``min_width_m / 2`` (a negative buffer by that much leaves something). Thin
slivers between strips, even fully walled ones, fail this. Parts smaller than
these are dropped one by one, so a good face is kept even if a sliver is not.

Output.  A valid Polygon or MultiPolygon in WGS-84 (x=lng, y=lat) of NEW land:
it never overlaps the input territory and never leaves its convex hull. None
when nothing qualifies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .territory_shape import _clean, _polygonal

_MIN_PART_SQ_M = 0.01  # polygon parts smaller than this (m²) are numerical dust
_MIN_PART_SQ_DEG = 1e-12  # the same dust in square degrees (~0.01 m² near the equator)


@dataclass(frozen=True)
class EnclosureConfig:
    # Largest gap (m) between two pieces of territory that still counts as closed.
    # Covers GPS error and a run that stopped short of the next street.
    gap_m: float = 20.0
    # Smallest enclosed part (m²) worth filling; matches the loop minimum.
    min_area_sq_m: float = 200.0
    # An enclosed part must be wider than this (m) somewhere, i.e. hold a disc of
    # diameter min_width_m; matches the 30 m rule for guessed loop faces.
    min_width_m: float = 30.0
    # Segments per quarter circle for the round buffers (gap bridging).
    quad_segs: int = 8
    # Mitre limit (multiples of the distance) when growing a trimmed face back,
    # so corners stay square.
    mitre_limit: float = 5.0


# ---------------------------------------------------------------- helpers


class _Frame:
    """Local azimuthal equidistant frame in metres, centred on (lat0, lng0)."""

    def __init__(self, lat0: float, lng0: float):
        crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={lat0!r} +lon_0={lng0!r} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )
        wgs = CRS.from_epsg(4326)
        self._fwd = Transformer.from_crs(wgs, crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, wgs, always_xy=True)

    @staticmethod
    def _apply(tr: Transformer, geom: BaseGeometry) -> BaseGeometry:
        def f(coords):
            x, y = tr.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])

        return shapely.transform(geom, f)

    def to_xy(self, geom: BaseGeometry) -> BaseGeometry:
        return self._apply(self._fwd, geom)

    def to_lnglat(self, geom: BaseGeometry) -> BaseGeometry:
        return self._apply(self._inv, geom)


def _parts(geom: Optional[BaseGeometry]) -> list[Polygon]:
    geom = _polygonal(geom)
    if geom is None:
        return []
    return [p for p in getattr(geom, "geoms", [geom]) if not p.is_empty]


def _holes(geom: BaseGeometry) -> list[Polygon]:
    return [Polygon(r) for p in _parts(geom) for r in p.interiors]


def _fill(geom: BaseGeometry) -> BaseGeometry:
    return unary_union([Polygon(p.exterior) for p in _parts(geom)])


def _bridged_faces(terr: BaseGeometry, hull: BaseGeometry, cfg: EnclosureConfig) -> list[Polygon]:
    """Faces walled off by the territory once gaps up to gap_m are bridged (see module notes)."""
    g = cfg.gap_m / 2.0
    dilated = terr.buffer(g, quad_segs=cfg.quad_segs)
    seeds = [h for h in _holes(dilated) if h.area > _MIN_PART_SQ_M]
    if not seeds:
        return []
    closed = _fill(dilated).buffer(-g, quad_segs=cfg.quad_segs)
    cand = _parts(closed.intersection(hull).difference(terr))
    if not cand:
        return []
    tree = shapely.STRtree(cand)
    hit = set()
    for s in seeds:
        # A point well inside the seed: robust against touching boundaries.
        idx = tree.query(s.representative_point(), predicate="intersects")
        hit.update(int(i) for i in idx)
    faces: list[Polygon] = []
    for i in sorted(hit):
        face = cand[i]
        shrunk = face.buffer(-g, quad_segs=cfg.quad_segs)
        if shrunk.is_empty:
            continue
        grown = shrunk.buffer(g, join_style="mitre", mitre_limit=cfg.mitre_limit)
        faces.extend(_parts(grown.intersection(face)))
    return faces


# ---------------------------------------------------------------- API


def enclosed_by(
    territory: Optional[BaseGeometry],
    config: EnclosureConfig = EnclosureConfig(),
) -> Optional[BaseGeometry]:
    """NEW land walled off by the runner's territory, or None.

    territory: shapely Polygon/MultiPolygon in WGS-84 (x=lng, y=lat), the
    runner's whole territory. Invalid input is repaired; non-polygonal parts
    are ignored. The result never overlaps the territory and stays inside its
    convex hull.
    """
    cfg = config
    if territory is None or territory.is_empty:
        return None
    if not territory.is_valid:
        territory = shapely.make_valid(territory)
    terr_ll = _clean(territory, 0.0)
    if terr_ll is None:
        return None
    minx, miny, maxx, maxy = terr_ll.bounds
    frame = _Frame((miny + maxy) / 2.0, (minx + maxx) / 2.0)
    terr = _clean(frame.to_xy(terr_ll), _MIN_PART_SQ_M)
    if terr is None:
        return None
    hull = terr.convex_hull
    if hull.area <= cfg.min_area_sq_m:
        return None

    faces = [p for h in _holes(terr) for p in _parts(h.difference(terr))]
    if cfg.gap_m > 0:
        faces += _bridged_faces(terr, hull, cfg)
    if not faces:
        return None

    merged = _parts(unary_union(faces).intersection(hull).difference(terr))
    r = cfg.min_width_m / 2.0
    keep = [
        p for p in merged
        if p.area >= cfg.min_area_sq_m and (r <= 0 or not p.buffer(-r, quad_segs=cfg.quad_segs).is_empty)
    ]
    if not keep:
        return None
    out_xy = keep[0] if len(keep) == 1 else MultiPolygon(keep)
    out = _clean(frame.to_lnglat(out_xy), 0.0)
    if out is None:
        return None
    # Transform round-off can leave a hair of overlap along shared edges.
    return _clean(out.difference(terr_ll), _MIN_PART_SQ_DEG)
