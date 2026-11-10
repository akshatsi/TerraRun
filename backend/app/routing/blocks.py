"""What each city block is worth to the runner (see planner.py for the design)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import shapely
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry


@dataclass
class BlockValues:
    area: np.ndarray  # m², per face
    mine: np.ndarray  # held by the runner
    stolen: np.ndarray  # held by followed friends (all of them)
    new: np.ndarray  # held by no one (that matters)
    new_value: np.ndarray  # new area with the section bonus
    stolen_value: np.ndarray  # steal_weight x friends' area, with the section bonus
    value: np.ndarray  # new_value + stolen_value


def section_multipliers(mine: Optional[BaseGeometry], radius_m: float, size_m: float,
                        lo: float, hi: float, bonus: float) -> tuple[dict[tuple[int, int], float], float]:
    """Section (ix, iy) -> score multiplier, for the square sections covering the search disc.

    Section (ix, iy) covers x in [(ix - 0.5) s, (ix + 0.5) s) and likewise
    for y, so the runner stands at the centre of section (0, 0).
    """
    out: dict[tuple[int, int], float] = {}
    if size_m <= 0 or mine is None or mine.is_empty or bonus == 1.0:
        return out, size_m
    n = int(math.ceil(radius_m / size_m + 0.5))
    keys, cells = [], []
    for ix in range(-n, n + 1):
        for iy in range(-n, n + 1):
            keys.append((ix, iy))
            cells.append(box((ix - 0.5) * size_m, (iy - 0.5) * size_m,
                             (ix + 0.5) * size_m, (iy + 0.5) * size_m))
    cells_a = np.array(cells, dtype=object)
    shapely.prepare(mine)
    hit = shapely.intersects(cells_a, mine)
    held = np.zeros(len(cells))
    if hit.any():
        held[hit] = shapely.area(shapely.intersection(cells_a[hit], mine))
    share = held / (size_m * size_m)
    for k, s in zip(keys, share):
        if lo <= s <= hi:
            out[k] = bonus
    return out, size_m


def value_blocks(polys: list[Optional[BaseGeometry]], mine: Optional[BaseGeometry],
                 friends: list[BaseGeometry], steal_weight: float,
                 sections: dict[tuple[int, int], float], size_m: float) -> BlockValues:
    """Split each block by section, then measure its land by holder.

    mine and friends are disjoint layers in the local frame (the planner
    makes them so). Area left over is new land.
    """
    n = len(polys)
    piece_geom, piece_face, piece_mult = [], [], []
    for f, g in enumerate(polys):
        if g is None or g.is_empty:
            continue
        if not sections:
            piece_geom.append(g)
            piece_face.append(f)
            piece_mult.append(1.0)
            continue
        x0, y0, x1, y1 = g.bounds
        ix0, ix1 = math.floor(x0 / size_m + 0.5), math.floor(x1 / size_m + 0.5)
        iy0, iy1 = math.floor(y0 / size_m + 0.5), math.floor(y1 / size_m + 0.5)
        if ix0 == ix1 and iy0 == iy1:
            piece_geom.append(g)
            piece_face.append(f)
            piece_mult.append(sections.get((ix0, iy0), 1.0))
            continue
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                cell = box((ix - 0.5) * size_m, (iy - 0.5) * size_m, (ix + 0.5) * size_m, (iy + 0.5) * size_m)
                p = g.intersection(cell)
                if not p.is_empty and p.area > 0:
                    piece_geom.append(p)
                    piece_face.append(f)
                    piece_mult.append(sections.get((ix, iy), 1.0))
    pg = np.array(piece_geom, dtype=object)
    pf = np.array(piece_face, dtype=int)
    pm = np.array(piece_mult, dtype=float)
    parea = shapely.area(pg) if len(pg) else np.zeros(0)

    def layer_area(layer: Optional[BaseGeometry]) -> np.ndarray:
        a = np.zeros(len(pg))
        if layer is None or layer.is_empty or not len(pg):
            return a
        shapely.prepare(layer)
        hit = shapely.intersects(pg, layer)
        if hit.any():
            a[hit] = shapely.area(shapely.intersection(pg[hit], layer))
        return a

    p_mine = layer_area(mine)
    p_stolen = np.zeros(len(pg))
    for layer in friends:
        p_stolen += layer_area(layer)
    p_new = np.clip(parea - p_mine - p_stolen, 0.0, None)

    def per_face(v: np.ndarray) -> np.ndarray:
        out = np.zeros(n)
        if len(v):
            np.add.at(out, pf, v)
        return out

    new_value = per_face(pm * p_new)
    stolen_value = per_face(pm * steal_weight * p_stolen)
    return BlockValues(
        area=per_face(parea), mine=per_face(p_mine), stolen=per_face(p_stolen), new=per_face(p_new),
        new_value=new_value, stolen_value=stolen_value, value=new_value + stolen_value,
    )
