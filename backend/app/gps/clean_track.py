"""Clean tracks (v4): snap GPS to the way the runner was on. Pure Python; no database.

Raw GPS wanders left and right on a straight road, so the recorded line looks
ragged and its 3 m territory strip breaks into patches. ``clean_track`` turns
the accepted fixes into a line that follows the road or path the runner was
actually on (see docs/gps-accuracy.md section 6):

* **On a way:** map matching over the way network. The output is the path
  along the network between matched points, so a straight road comes out
  straight and turns happen at junctions.
* **Off any way** (parks, open ground, missing map data): the runner's own line,
  smoothed to remove the wobble and simplified, never moved onto a road.
* Segments are kept: the same number come out as went in, and nothing is
  joined across a gap. Segments with fewer than 2 points pass through.

Design notes
------------
Projection.  All work happens in metres in an azimuthal equidistant frame
(``+proj=aeqd``, WGS-84) centred on the run, built per call, as in
``territory_shape``. Ways farther than ``way_margin_m`` from the run's
bounding box are dropped before anything else.

Network.  Each way is split into straight edges between its consecutive
points. Points from different ways within ``node_snap_m`` of each other become
one node, so ways that share an OSM node (or nearly so) connect, and a way
that ends within ``node_snap_m`` of the middle of another way's edge is joined
to it there (a T-junction drawn without a shared node). Only ways
whose ``highway`` is in ``walkable_highways`` (or is a ``_link`` of one) are
used.

Candidates.  For each fix, the nearest points on every edge within its snap
radius ``clamp(snap_accuracy_factor x accuracy, min_snap_m, max_snap_m)``,
found with an STRtree, at most ``max_candidates`` per fix. A point clamped
to an edge's end node is dropped when the fix projects onto a neighbouring
edge at that node instead, so the nearest candidate is the fix's true
projection onto the network. A fix with no
candidate is off-network: the best way is too far to trust (but up to
``max_skip_fixes`` such fixes in a row inside a matched stretch are treated as
stray fixes and stepped over). A projection past
the end of a dead-end way by more than ``dead_end_overrun_m`` is not a
candidate, so a runner leaving the end of a mapped path into a park is not
pinned to its last node.

Matching.  A hidden Markov model solved with Viterbi (Newson and Krumm,
2009). Emission: Gaussian on the distance from fix to candidate, sigma =
the fix's accuracy clamped to ``[emission_min_sigma_m, emission_max_sigma_m]``.
Transition: ``-|route - straight| / transition_beta_m``, where ``route`` is the
shortest network distance between the two candidates (bounded Dijkstra, cached
per node) and ``straight`` the distance between the two fixes after smoothing
(raw fixes zig-zag, and matching their straight-line steps would make the
match zig-zag back and forth along the road). A transition is impossible when
the route is longer than ``detour_ratio x straight + detour_slack_m`` (taking
the larger of the raw and smoothed step); when every transition into a fix is impossible, the chain
breaks there and a new one starts. Walking is undirected, so one-way tags are
ignored.

Trust.  A matched chain counts only if it has at least ``min_chain_fixes``
fixes and its matched path (after the clean-up below) is no longer than
``chain_detour_ratio`` x the smoothed GPS length + ``chain_detour_slack_m``. Other fixes are off-network.

Matched output.  The network path through the matched points. GPS noise along
the road makes the match step back and forth a little; any short excursion
that leaves a point and comes back to it within ``spike_max_m`` is cut out,
then collinear points are dropped. The path starts and ends at the
projections of the stretch's first and last fixes.

Off-network output.  A Gaussian moving average over neighbouring fixes (sigma
``smooth_sigma_fixes``), each fix weighted by 1/accuracy^2, removes the
left-right wobble. Its window shrinks symmetrically towards the segment's
ends, so the first and last fixes are kept and a straight track is not
shortened. Then Douglas-Peucker at ``simplify_tolerance_m``. Smoothing rounds
corners off by a few metres, so each turn of at least ``corner_min_turn_deg``
then moves (at most ``corner_max_move_m``) to where straight lines fitted to
the raw fixes of the two legs meet. An off stretch starts where the previous
matched stretch ends and ends where the next one starts, so the line has no
jumps.

Result.  ``matched_fraction`` is the share of the cleaned length that lies on
a way (connectors and off stretches count as off). ``method`` is ``matched``
when that share is at least ``matched_method_fraction``, ``smoothed`` when
nothing matched (or no ways were given), ``mixed`` otherwise, and ``raw`` when
no segment had 2 points or cleaning failed; then the input comes back
unchanged.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import LineString

from .geodesy import valid_coordinate

LatLng = tuple[float, float]
XY = tuple[float, float]

_EPS_M = 0.01  # points closer than this are the same point

_WALKABLE = frozenset({
    "footway", "path", "pedestrian", "steps", "track", "cycleway", "service",
    "residential", "living_street", "unclassified", "tertiary", "secondary",
    "primary", "trunk", "corridor",
})


@dataclass(frozen=True)
class WalkWay:
    osm_id: int
    highway: str
    points: list[LatLng]  # (lat, lng), in way order


@dataclass(frozen=True)
class CleanConfig:
    # Ways used for matching. A value ending in "_link" counts if its base does.
    walkable_highways: frozenset = _WALKABLE
    way_margin_m: float = 100.0  # ways farther than this (m) from the run's bounding box are ignored
    node_snap_m: float = 1.0  # way points closer than this (m) become one network node
    default_accuracy_m: float = 10.0  # accuracy (m) assumed for a fix that reports none
    snap_accuracy_factor: float = 2.5  # snap radius = this x accuracy ...
    min_snap_m: float = 12.0  # ... but at least this (m), since phones under-report accuracy ...
    max_snap_m: float = 25.0  # ... and at most this (m): a way farther away is never trusted
    max_candidates: int = 6  # candidate points per fix (nearest first)
    dead_end_overrun_m: float = 5.0  # a fix more than this (m) past a dead end gets no candidate there
    emission_min_sigma_m: float = 4.0  # emission sigma (m) = accuracy clamped to this ...
    emission_max_sigma_m: float = 15.0  # ... and this
    transition_beta_m: float = 5.0  # metres of |route - straight| per unit of log-probability
    detour_ratio: float = 2.0  # one step's route may be at most this x the straight distance ...
    detour_slack_m: float = 15.0  # ... plus this (m); longer and the match breaks
    max_skip_fixes: int = 2  # this many stray fixes in a row with no way in reach stay inside a match
    min_chain_fixes: int = 3  # a matched stretch needs at least this many fixes
    chain_detour_ratio: float = 1.5  # a stretch's route may be at most this x its smoothed GPS length ...
    chain_detour_slack_m: float = 40.0  # ... plus this (m); longer and it stays off-network
    spike_max_m: float = 50.0  # matched back-and-forth excursions up to this long (m) are cut out (2 x max_snap_m)
    spike_tolerance_m: float = 1.0  # ... when the path comes back within this (m) of where it left
    matched_simplify_m: float = 0.1  # drop matched points within this (m) of a straight line
    smooth_sigma_fixes: float = 2.5  # Gaussian moving-average sigma, in fixes, for off-network stretches ...
    smooth_sigma_max_m: float = 6.0  # ... but never wider than this along the track (m), so sparse fixes keep their shape
    smooth_accuracy_floor_m: float = 3.0  # accuracy (m) below this is treated as this when weighting
    simplify_tolerance_m: float = 3.0  # Douglas-Peucker tolerance (m) for off-network stretches
    corner_min_turn_deg: float = 30.0  # an off-network turn this sharp or sharper gets its corner back ...
    corner_max_move_m: float = 10.0  # ... by moving the vertex at most this far (m)
    matched_method_fraction: float = 0.9  # method is "matched" at or above this matched share


@dataclass
class CleanTrack:
    segments: list[list[LatLng]]  # cleaned (lat, lng) per input segment, same count
    method: str  # "matched" | "smoothed" | "mixed" | "raw"
    matched_fraction: float  # share of cleaned length on a way, 0..1
    notes: str = ""  # short text for logs


# ---------------------------------------------------------------- geometry helpers


class _Frame:
    """Local azimuthal equidistant frame in metres, centred on the run."""

    def __init__(self, lat0: float, lng0: float):
        crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={lat0!r} +lon_0={lng0!r} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )
        wgs = CRS.from_epsg(4326)
        self._fwd = Transformer.from_crs(wgs, crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, wgs, always_xy=True)

    def to_xy(self, lat: np.ndarray, lng: np.ndarray) -> np.ndarray:
        x, y = self._fwd.transform(lng, lat)
        return np.column_stack([np.asarray(x, float), np.asarray(y, float)])

    def to_latlng(self, xy: Sequence[XY]) -> list[LatLng]:
        if not xy:
            return []
        a = np.asarray(xy, float)
        lng, lat = self._inv.transform(a[:, 0], a[:, 1])
        return [(float(la), float(ln)) for la, ln in zip(np.atleast_1d(lat), np.atleast_1d(lng))]


def _dist(a: XY, b: XY) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _length(pts: Sequence[XY]) -> float:
    return sum(_dist(a, b) for a, b in zip(pts, pts[1:]))


def _dedupe(pts: Sequence[XY]) -> list[XY]:
    out: list[XY] = []
    for p in pts:
        if not out or _dist(p, out[-1]) > _EPS_M:
            out.append(p)
    return out


def _simplify(pts: Sequence[XY], tol: float) -> list[XY]:
    pts = _dedupe(pts)
    if len(pts) < 3 or tol <= 0:
        return list(pts)
    line = LineString(pts).simplify(tol, preserve_topology=False)
    return [(float(x), float(y)) for x, y in line.coords]


def _remove_spikes(pts: list[XY], max_len: float, tol: float) -> list[XY]:
    """Cut out short excursions that leave a point and come back to it.

    Map matching on a noisy track steps back along the road and forward again,
    or a few metres up a side street and back to the junction. From each point,
    walk on up to max_len: if the path comes back within tol of that point
    after at least tol of walking, the part in between is cut out. A real
    out-and-back never comes back to where it turned, so it stays. The first
    and last points are always kept.
    """
    pts = _dedupe(pts)
    i = 0
    while i < len(pts) - 2:
        p = pts[i]
        walked = 0.0
        cut = None
        j = i + 1
        while j < len(pts) - 1 and walked <= max_len:
            a, b = pts[j], pts[j + 1]
            walked += _dist(pts[j - 1], a)
            dx, dy = b[0] - a[0], b[1] - a[1]
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
            back = math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
            if back <= tol and walked + t * math.sqrt(l2) >= tol:
                cut = j
                break
            j += 1
        if cut is None:
            i += 1
            continue
        pts = _dedupe(pts[: i + 1] + pts[cut + 1:])
        i = max(0, i - 1)
    return pts


def _smooth(xy: np.ndarray, acc: np.ndarray, cfg: CleanConfig, adaptive: bool = True) -> np.ndarray:
    """Gaussian moving average over fixes, each weighted by 1/accuracy^2.

    The window is symmetric and shrinks towards the ends of the segment (a fix
    k places from an end averages over at most k fixes each side), so a
    straight track is not shortened and the first and last fixes are kept.
    """
    n = len(xy)
    s = cfg.smooth_sigma_fixes
    if n < 3 or s <= 0:
        return xy.copy()
    # The window may span at most max(smooth_sigma_max_m, 3 x the wobble) metres,
    # wobble being the median offset of a fix from the midpoint of its
    # neighbours. A zig-zag gets the full window; sparse fixes on a real curve
    # (a small loop) keep their shape instead of being pulled inward.
    steps = np.hypot(*np.diff(xy, axis=0).T)
    step = float(np.median(steps[steps > 0])) if np.any(steps > 0) else 0.0
    wobble = float(np.median(np.hypot(*(xy[1:-1] - 0.5 * (xy[:-2] + xy[2:])).T)))
    if adaptive and step > 0:
        s = min(s, max(cfg.smooth_sigma_max_m, 3.0 * wobble) / step)
    if s < 0.3:  # under a third of a fix: smoothing would do nothing
        return xy.copy()
    w_acc = 1.0 / np.maximum(acc, cfg.smooth_accuracy_floor_m) ** 2
    reach = np.minimum(np.arange(n), np.arange(n)[::-1])  # fixes available on both sides
    half = int(math.ceil(3 * s))
    num = np.zeros_like(xy)
    den = np.zeros(n)
    for k in range(-half, half + 1):
        kern = math.exp(-0.5 * (k / s) ** 2)
        lo, hi = max(0, -k), min(n, n - k)  # i in [lo, hi) uses fix i + k
        if lo >= hi:
            continue
        w = kern * w_acc[lo + k: hi + k] * (reach[lo:hi] >= abs(k))
        num[lo:hi] += w[:, None] * xy[lo + k: hi + k]
        den[lo:hi] += w
    return num / den[:, None]


def _dp_indices(pts: np.ndarray, tol: float) -> list[int]:
    """Douglas-Peucker on pts, returning the indices of the points kept."""
    n = len(pts)
    if n < 3:
        return list(range(n))
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        seg = pts[a + 1: b]
        d = pts[b] - pts[a]
        ln = math.hypot(d[0], d[1])
        if ln == 0:
            dist = np.hypot(*(seg - pts[a]).T)
        else:
            dist = np.abs(d[0] * (seg[:, 1] - pts[a, 1]) - d[1] * (seg[:, 0] - pts[a, 0])) / ln
        k = int(np.argmax(dist))
        if dist[k] > tol:
            m = a + 1 + k
            keep[m] = True
            stack += [(a, m), (m, b)]
    return [int(i) for i in np.flatnonzero(keep)]


def _fit_line(pts: np.ndarray, w: np.ndarray) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Weighted total-least-squares line: (a point on it, unit direction)."""
    if len(pts) < 2 or w.sum() <= 0:
        return None
    c = (pts * w[:, None]).sum(axis=0) / w.sum()
    q = pts - c
    cov = (q * w[:, None]).T @ q
    vals, vecs = np.linalg.eigh(cov)
    if vals[-1] <= 1e-9:
        return None
    return c, vecs[:, -1]


def _shape(smooth: np.ndarray, raw: np.ndarray, w: np.ndarray, cfg: CleanConfig) -> list[XY]:
    """Simplify a smoothed stretch and put its real turns back where they were.

    Smoothing rounds a corner off by a few metres. After Douglas-Peucker, each
    kept vertex where the line turns by at least ``corner_min_turn_deg`` moves
    to where straight lines fitted to the raw fixes of the two legs meet, if
    that is within ``corner_max_move_m``. The fits leave out the fixes nearest
    each end of a leg, which belong to the turn. End points never move.
    """
    idx = _dp_indices(smooth, cfg.simplify_tolerance_m)
    out = smooth[idx].copy()
    if len(idx) < 3 or cfg.corner_max_move_m <= 0:
        return [(float(x), float(y)) for x, y in out]
    trim = int(math.ceil(2 * cfg.smooth_sigma_fixes))
    lines = []
    for a, b in zip(idx, idx[1:]):
        m = max(0, min(trim, (b - a - 2) // 2))
        lines.append(_fit_line(raw[a + m: b - m + 1], w[a + m: b - m + 1]))
    min_sin = math.sin(math.radians(cfg.corner_min_turn_deg))
    for k in range(1, len(idx) - 1):
        l1, l2 = lines[k - 1], lines[k]
        if l1 is None or l2 is None:
            continue
        (c1, d1), (c2, d2) = l1, l2
        # The turn at this vertex, from the simplified line itself.
        u = out[k] - out[k - 1]
        v = out[k + 1] - out[k]
        nu, nv = np.hypot(*u), np.hypot(*v)
        if nu == 0 or nv == 0:
            continue
        cos_turn = float(u @ v) / (nu * nv)
        if cos_turn > math.cos(math.radians(cfg.corner_min_turn_deg)):
            continue
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(cross) < min_sin:
            continue
        diff = c2 - c1
        t = (diff[0] * d2[1] - diff[1] * d2[0]) / cross
        q = c1 + t * d1
        if np.hypot(*(q - out[k])) <= cfg.corner_max_move_m:
            out[k] = q
    return [(float(x), float(y)) for x, y in out]


# ---------------------------------------------------------------- way network


def _walkable(highway: str, allowed: frozenset) -> bool:
    h = (highway or "").strip().lower()
    if h in allowed:
        return True
    return h.endswith("_link") and h[: -len("_link")] in allowed


class _Network:
    """Undirected graph of straight edges between merged way points."""

    def __init__(self, ways_xy: list[np.ndarray], cfg: CleanConfig):
        snap = max(cfg.node_snap_m, 1e-6)
        self.node_xy: list[XY] = []
        grid: dict[tuple[int, int], list[int]] = {}
        edges: dict[tuple[int, int], float] = {}

        def node_for(x: float, y: float) -> int:
            gx, gy = int(math.floor(x / snap)), int(math.floor(y / snap))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for nid in grid.get((gx + dx, gy + dy), ()):
                        nx, ny = self.node_xy[nid]
                        if math.hypot(nx - x, ny - y) <= snap:
                            return nid
            nid = len(self.node_xy)
            self.node_xy.append((x, y))
            grid.setdefault((gx, gy), []).append(nid)
            return nid

        for pts in ways_xy:
            prev = None
            for x, y in pts:
                nid = node_for(float(x), float(y))
                if prev is not None and nid != prev:
                    key = (min(prev, nid), max(prev, nid))
                    if key not in edges:
                        edges[key] = _dist(self.node_xy[prev], self.node_xy[nid])
                prev = nid
        edges = self._split_at_t_junctions(edges, snap)

        self.adj: list[list[tuple[int, float]]] = [[] for _ in self.node_xy]
        keys = [k for k, ln in edges.items() if ln > _EPS_M]
        self.eu = np.array([k[0] for k in keys], dtype=int)
        self.ev = np.array([k[1] for k in keys], dtype=int)
        self.elen = np.array([edges[k] for k in keys], dtype=float)
        for u, v, ln in zip(self.eu, self.ev, self.elen):
            self.adj[u].append((int(v), float(ln)))
            self.adj[v].append((int(u), float(ln)))
        self.degree = np.array([len(a) for a in self.adj], dtype=int)
        nxy = np.asarray(self.node_xy, float).reshape(-1, 2)
        if len(keys):
            self.a = nxy[self.eu]
            self.b = nxy[self.ev]
            self.tree = shapely.STRtree(shapely.linestrings(np.stack([self.a, self.b], axis=1)))
        else:
            self.a = self.b = np.zeros((0, 2))
            self.tree = None
        self._cache: dict[int, tuple[float, dict[int, float], dict[int, int]]] = {}

    def _split_at_t_junctions(self, edges: dict[tuple[int, int], float],
                              snap: float) -> dict[tuple[int, int], float]:
        """Join a way that ends on another way's edge without a shared point.

        Each way end within ``snap`` of the middle of another edge becomes a
        node on that edge, so the two ways connect.
        """
        keys = [k for k, ln in edges.items() if ln > _EPS_M]
        if not keys:
            return edges
        deg: dict[int, int] = {}
        for u, v in keys:
            deg[u] = deg.get(u, 0) + 1
            deg[v] = deg.get(v, 0) + 1
        ends = [n for n, d in deg.items() if d == 1]
        if not ends:
            return edges
        nxy = np.asarray(self.node_xy, float)
        tree = shapely.STRtree(shapely.linestrings(
            np.stack([nxy[[k[0] for k in keys]], nxy[[k[1] for k in keys]]], axis=1)))
        ni, ei = tree.query(shapely.points(nxy[ends]), predicate="dwithin", distance=snap)
        inserts: dict[tuple[int, int], list[tuple[float, int]]] = {}
        for a, e in zip(ni, ei):
            n, (u, v) = ends[a], keys[e]
            if n in (u, v):
                continue
            (ux, uy), (vx, vy), (px, py) = nxy[u], nxy[v], nxy[n]
            dx, dy = vx - ux, vy - uy
            t = ((px - ux) * dx + (py - uy) * dy) / (dx * dx + dy * dy)
            if 0.0 < t < 1.0:
                inserts.setdefault((u, v), []).append((t, n))
        out = dict(edges)
        for (u, v), mids in inserts.items():
            del out[(u, v)]
            chain = [u] + [n for _, n in sorted(set(mids))] + [v]
            for p, q in zip(chain, chain[1:]):
                if p != q:
                    out.setdefault((min(p, q), max(p, q)), _dist(self.node_xy[p], self.node_xy[q]))
        return out

    @property
    def n_edges(self) -> int:
        return len(self.elen)

    def _tree_from(self, src: int, bound: float) -> tuple[dict[int, float], dict[int, int]]:
        """Shortest distances from src up to bound, with predecessors. Cached."""
        hit = self._cache.get(src)
        if hit is not None and hit[0] >= bound:
            return hit[1], hit[2]
        bound = max(bound, hit[0] * 2 if hit else 0.0)  # grow geometrically to limit recomputes
        dist = {src: 0.0}
        pred: dict[int, int] = {}
        heap = [(0.0, src)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, math.inf):
                continue
            for v, ln in self.adj[u]:
                nd = d + ln
                if nd <= bound and nd < dist.get(v, math.inf):
                    dist[v] = nd
                    pred[v] = u
                    heapq.heappush(heap, (nd, v))
        self._cache[src] = (bound, dist, pred)
        return dist, pred

    def route(self, ca: "_Cand", cb: "_Cand", bound: float) -> Optional[tuple[float, tuple]]:
        """Shortest network distance between two candidates, if within bound."""
        best: Optional[tuple[float, tuple]] = None
        if ca.edge == cb.edge:
            best = (abs(ca.off - cb.off), ("direct",))
        la, lb = self.elen[ca.edge], self.elen[cb.edge]
        ends_a = ((int(self.eu[ca.edge]), ca.off), (int(self.ev[ca.edge]), la - ca.off))
        ends_b = ((int(self.eu[cb.edge]), cb.off), (int(self.ev[cb.edge]), lb - cb.off))
        for s, sc in ends_a:
            if sc > bound or (best is not None and sc >= best[0]):
                continue
            dist, _ = self._tree_from(s, bound)
            for e, ec in ends_b:
                d = dist.get(e)
                if d is None:
                    continue
                total = sc + d + ec
                if total <= bound and (best is None or total < best[0] - 1e-9):
                    best = (total, ("via", s, e))
        return best

    def path(self, ca: "_Cand", cb: "_Cand", key: tuple) -> list[XY]:
        if key[0] == "direct":
            return [ca.xy, cb.xy]
        _, s, e = key
        _, _, pred = self._cache[s]
        nodes = [e]
        while nodes[-1] != s:
            nodes.append(pred[nodes[-1]])
        nodes.reverse()
        return [ca.xy] + [self.node_xy[n] for n in nodes] + [cb.xy]


@dataclass
class _Cand:
    edge: int
    off: float  # metres from the edge's first node
    xy: XY
    dist: float  # metres from the fix


def _candidates(net: _Network, xy: np.ndarray, radius: np.ndarray,
                cfg: CleanConfig) -> list[list[_Cand]]:
    out: list[list[_Cand]] = [[] for _ in range(len(xy))]
    if net.tree is None or len(xy) == 0:
        return out
    fi, ei = net.tree.query(shapely.points(xy), predicate="dwithin", distance=radius)
    if len(fi) == 0:
        return out
    p = xy[fi]
    a, b = net.a[ei], net.b[ei]
    d = b - a
    l2 = np.einsum("ij,ij->i", d, d)
    t_raw = np.einsum("ij,ij->i", p - a, d) / l2
    t = np.clip(t_raw, 0.0, 1.0)
    proj = a + t[:, None] * d
    dist = np.hypot(*(p - proj).T)
    ln = np.sqrt(l2)
    over_u = (-t_raw * ln > cfg.dead_end_overrun_m) & (net.degree[net.eu[ei]] == 1)
    over_v = ((t_raw - 1.0) * ln > cfg.dead_end_overrun_m) & (net.degree[net.ev[ei]] == 1)
    keep = (dist <= radius[fi] + 1e-9) & ~over_u & ~over_v
    order = np.lexsort((dist, fi))
    for k in order:
        if not keep[k]:
            continue
        lst = out[fi[k]]
        if len(lst) >= cfg.max_candidates:
            continue
        c_xy = (float(proj[k, 0]), float(proj[k, 1]))
        if any(_dist(c_xy, c.xy) < 0.5 for c in lst):
            continue  # same place reached through another edge (a shared node)
        if t[k] in (0.0, 1.0):
            # Clamped to a node: if a nearer candidate lies on another edge at
            # that node, the fix projects onto that edge and this adds nothing.
            node = net.eu[ei[k]] if t[k] == 0.0 else net.ev[ei[k]]
            if any(node in (net.eu[c.edge], net.ev[c.edge]) for c in lst):
                continue
        lst.append(_Cand(int(ei[k]), float(t[k] * ln[k]), c_xy, float(dist[k])))
    return out


# ---------------------------------------------------------------- matching


@dataclass
class _Chain:
    start: int  # first fix index
    end: int  # last fix index (inclusive)
    path: list[XY]  # network path through the matched points
    route_m: float


def _viterbi(net: _Network, xy: np.ndarray, smooth: np.ndarray, acc: np.ndarray,
             cands: list[list[_Cand]], cfg: CleanConfig) -> list[_Chain]:
    """Chains of fixes matched to the network.

    Up to ``max_skip_fixes`` fixes in a row with no candidate (a stray fix)
    are stepped over and stay inside the chain; more than that ends it.
    """
    chains: list[_Chain] = []
    n = len(xy)
    sig = np.clip(acc, cfg.emission_min_sigma_m, cfg.emission_max_sigma_m)

    def emission(i: int) -> list[float]:
        return [-0.5 * (c.dist / sig[i]) ** 2 for c in cands[i]]

    # The open chain: fix indices with candidates, and per step the best
    # (previous candidate, route m, route key) for each candidate.
    steps: list[int] = []
    scores: list[float] = []
    backs: list[list[Optional[tuple[int, float, tuple]]]] = []

    def close() -> None:
        if not steps:
            return
        picks = [int(np.argmax(scores))]
        for k in range(len(steps) - 1, 0, -1):
            picks.append(backs[k][picks[-1]][0])
        picks.reverse()
        path: list[XY] = [cands[steps[0]][picks[0]].xy]
        route = 0.0
        for k in range(1, len(steps)):
            pj, r, key = backs[k][picks[k]]
            path.extend(net.path(cands[steps[k - 1]][pj], cands[steps[k]][picks[k]], key)[1:])
            route += r
        chains.append(_Chain(steps[0], steps[-1], path, route))

    def open_at(i: int, em: list[float]) -> None:
        nonlocal steps, scores, backs
        steps, scores, backs = [i], em, [[None] * len(cands[i])]

    for i in range(n):
        ci = cands[i]
        if not ci:
            if steps and i - steps[-1] > cfg.max_skip_fixes:
                close()
                steps = []
            continue
        em = emission(i)
        if not steps:
            open_at(i, em)
            continue
        last = steps[-1]
        prev = cands[last]
        straight = float(np.hypot(*(smooth[i] - smooth[last])))
        raw = float(np.hypot(*(xy[i] - xy[last])))
        bound = cfg.detour_ratio * max(straight, raw) + cfg.detour_slack_m
        new_scores = [-math.inf] * len(ci)
        new_back: list[Optional[tuple[int, float, tuple]]] = [None] * len(ci)
        for pj, pc in enumerate(prev):
            if scores[pj] == -math.inf:
                continue
            for cj, cc in enumerate(ci):
                r = net.route(pc, cc, bound)
                if r is None:
                    continue
                sc = scores[pj] + em[cj] - abs(r[0] - straight) / cfg.transition_beta_m
                if sc > new_scores[cj]:
                    new_scores[cj] = sc
                    new_back[cj] = (pj, r[0], r[1])
        if all(sc == -math.inf for sc in new_scores):
            close()
            open_at(i, em)
            continue
        steps.append(i)
        scores = new_scores
        backs.append(new_back)
    close()
    return chains


# ---------------------------------------------------------------- per segment


def _clean_segment(xy: np.ndarray, acc: np.ndarray, net: Optional[_Network],
                   cfg: CleanConfig) -> tuple[list[XY], float, float, int]:
    """Cleaned points, matched length, total length, off-network stretch count."""
    # The matcher compares steps of a fully smoothed track with network
    # distances; the drawn off-network line uses the shape-keeping smoothing.
    match_smooth = _smooth(xy, acc, cfg, adaptive=False)
    smooth = _smooth(xy, acc, cfg)
    chains: list[_Chain] = []
    if net is not None and net.n_edges:
        radius = np.clip(cfg.snap_accuracy_factor * acc, cfg.min_snap_m, cfg.max_snap_m)
        cands = _candidates(net, xy, radius, cfg)
        for ch in _viterbi(net, xy, match_smooth, acc, cands, cfg):
            if ch.end - ch.start + 1 < cfg.min_chain_fixes:
                continue
            ch.path = _simplify(
                _remove_spikes(ch.path, cfg.spike_max_m, cfg.spike_tolerance_m),
                cfg.matched_simplify_m,
            )
            gps_len = float(np.hypot(*np.diff(match_smooth[ch.start: ch.end + 1], axis=0).T).sum())
            if _length(ch.path) > cfg.chain_detour_ratio * gps_len + cfg.chain_detour_slack_m:
                continue
            chains.append(ch)

    out: list[XY] = []
    matched_m = off_m = 0.0
    off_count = 0

    def add(pts: list[XY]) -> None:
        for p in pts:
            if not out or _dist(p, out[-1]) > _EPS_M:
                out.append(p)

    def add_off(lo: int, hi: int, head: Optional[XY], tail: Optional[XY]) -> None:
        """Smoothed fixes lo..hi-1, joined to the matched ends around them."""
        nonlocal off_m, off_count
        parts_s = ([np.array([head])] if head else []) + [smooth[lo:hi]] + ([np.array([tail])] if tail else [])
        parts_r = ([np.array([head])] if head else []) + [xy[lo:hi]] + ([np.array([tail])] if tail else [])
        a_s = np.concatenate([p.reshape(-1, 2) for p in parts_s])
        a_r = np.concatenate([p.reshape(-1, 2) for p in parts_r])
        w = np.concatenate([[1.0 / cfg.smooth_accuracy_floor_m ** 2] if head else [],
                            1.0 / np.maximum(acc[lo:hi], cfg.smooth_accuracy_floor_m) ** 2,
                            [1.0 / cfg.smooth_accuracy_floor_m ** 2] if tail else []])
        pts = _dedupe(_shape(a_s, a_r, w, cfg))
        if hi > lo:
            off_count += 1
        off_m += _length(pts)
        add(pts)

    cursor = 0
    head: Optional[XY] = None
    for ch in chains:
        if ch.start > cursor or head is not None:
            add_off(cursor, ch.start, head, ch.path[0])
        add(ch.path)
        matched_m += _length(ch.path)
        head = ch.path[-1]
        cursor = ch.end + 1
    if cursor < len(xy):
        add_off(cursor, len(xy), head, None)
    if len(out) < 2:  # everything collapsed onto one spot
        out = _dedupe([tuple(map(float, p)) for p in (smooth[0], smooth[-1])])
    return out, matched_m, matched_m + off_m, off_count


# ---------------------------------------------------------------- entry point


def _fmt_len(m: float) -> str:
    return f"{m / 1000:.1f} km" if m >= 1000 else f"{m:,.0f} m"


def clean_track(
    segments: list[list[LatLng]],
    accuracies: list[list[Optional[float]]],
    ways: list[WalkWay],
    config: CleanConfig = CleanConfig(),
) -> CleanTrack:
    """Clean each segment: matched to the way network where trusted, else smoothed."""
    segments = [list(s) for s in (segments or [])]
    try:
        return _clean(segments, accuracies or [], ways or [], config)
    except Exception as exc:  # never fail a run upload over cleaning; keep the raw line
        return CleanTrack(segments, "raw", 0.0, f"cleaning failed ({type(exc).__name__}: {exc}); raw track kept")


def _clean(segments: list[list[LatLng]], accuracies: list[list[Optional[float]]],
           ways: list[WalkWay], cfg: CleanConfig) -> CleanTrack:
    # Per segment: valid fixes with their accuracy, consecutive duplicates removed.
    prepared: list[Optional[tuple[list[LatLng], list[float]]]] = []
    for si, seg in enumerate(segments):
        accs = list(accuracies[si]) if si < len(accuracies) and accuracies[si] is not None else []
        pts: list[LatLng] = []
        acc: list[float] = []
        for k, p in enumerate(seg):
            lat, lng = float(p[0]), float(p[1])
            if not valid_coordinate(lat, lng):
                continue
            if pts and pts[-1] == (lat, lng):
                continue
            a = accs[k] if k < len(accs) else None
            a = float(a) if a is not None and math.isfinite(a) and a > 0 else cfg.default_accuracy_m
            pts.append((lat, lng))
            acc.append(a)
        prepared.append((pts, acc) if len(pts) >= 2 else None)

    if not any(prepared):
        return CleanTrack(segments, "raw", 0.0, "no segment with 2 or more fixes; nothing to clean")

    all_pts = [p for item in prepared if item for p in item[0]]
    lats = np.array([p[0] for p in all_pts])
    lngs = np.array([p[1] for p in all_pts])
    frame = _Frame(float((lats.min() + lats.max()) / 2), float((lngs.min() + lngs.max()) / 2))
    run_xy = frame.to_xy(lats, lngs)
    lo = run_xy.min(axis=0) - cfg.way_margin_m
    hi = run_xy.max(axis=0) + cfg.way_margin_m

    # Ways near the run, in metres.
    ways_xy: list[np.ndarray] = []
    used = [w for w in ways if _walkable(w.highway, cfg.walkable_highways)]
    way_pts = [[(float(la), float(ln)) for la, ln in w.points if valid_coordinate(float(la), float(ln))]
               for w in used]
    flat = [p for pts in way_pts for p in pts]
    if flat:
        wxy = frame.to_xy(np.array([p[0] for p in flat]), np.array([p[1] for p in flat]))
        k = 0
        for pts in way_pts:
            arr = wxy[k: k + len(pts)]
            k += len(pts)
            if len(arr) < 2:
                continue
            if (arr.max(axis=0) < lo).any() or (arr.min(axis=0) > hi).any():
                continue
            ways_xy.append(arr)
    net = _Network(ways_xy, cfg) if ways_xy else None

    out_segments: list[list[LatLng]] = []
    matched_m = total_m = 0.0
    off_count = 0
    for seg, item in zip(segments, prepared):
        if item is None:
            out_segments.append(list(seg))
            continue
        pts, acc = item
        xy = frame.to_xy(np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
        cleaned, m, t, offs = _clean_segment(xy, np.array(acc), net, cfg)
        matched_m += m
        total_m += t
        off_count += offs
        out_segments.append(frame.to_latlng(cleaned))

    frac = matched_m / total_m if total_m > 0 else 0.0
    frac = min(1.0, max(0.0, frac))
    if matched_m <= 0:
        method = "smoothed"
    elif frac >= cfg.matched_method_fraction:
        method = "matched"
    else:
        method = "mixed"
    n_edges = net.n_edges if net else 0
    notes = (
        f"{len(segments)} segment(s); {len(ways_xy)} of {len(ways)} ways nearby, {n_edges} edges; "
        f"{frac:.0%} of {_fmt_len(total_m)} matched; {off_count} off-network stretch(es)"
    )
    return CleanTrack(out_segments, method, frac, notes)
