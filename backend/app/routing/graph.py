"""Road graph and city blocks for the route finder (see planner.py for the design).

Everything here works in a local metric frame centred on the runner (x east,
y north, metres). The graph is planar by construction: roads are noded with
``shapely.union_all`` so that two roads only meet at a node. Its bounded faces are
the city blocks; they come from a half-edge walk, so every block knows exactly
which road pieces bound it and which block lies across each of them.
"""
from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import shapely
import shapely.ops
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

# Preference for each allowed highway class, 0 (least) .. 1 (most). Links take
# their parent's value. Unknown classes get a low value but stay usable.
CLASS_SCORE = {
    "trunk": 1.0, "primary": 0.9, "secondary": 0.75, "tertiary": 0.6,
    "unclassified": 0.4, "residential": 0.3, "living_street": 0.15, "service": 0.0,
}
_UNKNOWN_CLASS_SCORE = 0.2

_GRID_M = 0.01  # noding precision: coordinates snap to a 1 cm grid
_OVERSHOOT_M = 0.5  # a gap connector runs this far past the road it joins, so noding sees a crossing


def class_score(highway: str) -> float:
    h = (highway or "").strip().lower()
    if h.endswith("_link"):
        h = h[: -len("_link")]
    return CLASS_SCORE.get(h, _UNKNOWN_CLASS_SCORE)


class LocalFrame:
    """Azimuthal equidistant frame (WGS-84) centred on the runner, in metres.

    The same projection territory_shape uses. Within 3 km of the centre the
    area scale error is below 1e-7, so planar areas here are geodesic areas
    for every practical purpose.
    """

    def __init__(self, lat0: float, lng0: float):
        crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={lat0!r} +lon_0={lng0!r} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )
        wgs = CRS.from_epsg(4326)
        self._fwd = Transformer.from_crs(wgs, crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, wgs, always_xy=True)

    def to_xy(self, latlng: Sequence[tuple[float, float]]) -> np.ndarray:
        if len(latlng) == 0:
            return np.zeros((0, 2))
        a = np.asarray(latlng, dtype=float)
        x, y = self._fwd.transform(a[:, 1], a[:, 0])
        return np.column_stack([x, y])

    def to_latlng(self, xy: np.ndarray) -> list[tuple[float, float]]:
        a = np.asarray(xy, dtype=float)
        lng, lat = self._inv.transform(a[:, 0], a[:, 1])
        return [(float(la), float(ln)) for la, ln in zip(lat, lng)]

    def geom_to_xy(self, geom: BaseGeometry) -> BaseGeometry:
        def f(c):
            x, y = self._fwd.transform(c[:, 0], c[:, 1])
            return np.column_stack([x, y])
        return shapely.transform(geom, f)

    def geom_to_lnglat(self, geom: BaseGeometry) -> BaseGeometry:
        def f(c):
            lng, lat = self._inv.transform(c[:, 0], c[:, 1])
            return np.column_stack([lng, lat])
        return shapely.transform(geom, f)


# ---------------------------------------------------------------- network


@dataclass
class Network:
    """Undirected planar road graph. Edge e runs from node ea[e] to node eb[e]."""

    node_xy: list[tuple[float, float]]
    ea: list[int]
    eb: list[int]
    coords: list[np.ndarray]  # (k, 2) points of edge e, from ea to eb
    length: list[float]
    pref: list[float]  # road preference 0..1 (class and popularity)
    rank: list[float]  # class score alone, for coarsening
    near: list[bool]  # within start_radius of the runner
    osm: list[int]
    active: list[int]  # edge ids in use (on some cycle, in a component near the start)
    full: list[int]  # every edge of those components, dead ends included (for approach legs)


@dataclass
class _Part:
    line: LineString
    pref: float
    rank: float
    osm: int


def _gap_connectors(parts: list[_Part], snap_m: float) -> list[_Part]:
    """Short lines that close OSM gaps: a road end that stops near another road.

    For each line end that does not already touch another line, the nearest
    point on any other line within snap_m is found; the connector runs from
    the end to that point and 0.5 m past it, so noding sees a crossing (the
    stub past the road is a dead end and is pruned later). A line's end may
    also join its own other end (a ring drawn with a small gap).
    """
    if snap_m <= 0 or not parts:
        return []
    lines = [p.line for p in parts]
    tree = shapely.STRtree(lines)
    ends, owners = [], []
    for i, ln in enumerate(lines):
        c = ln.coords
        ends.append(Point(c[0]))
        ends.append(Point(c[-1]))
        owners += [i, i]
    qi, li = tree.query(ends, predicate="dwithin", distance=snap_m)
    near: dict[int, list[int]] = defaultdict(list)
    for q, j in zip(qi.tolist(), li.tolist()):
        near[q].append(j)
    out: list[_Part] = []
    for k in sorted(near):
        own = owners[k]
        p = ends[k]
        best: Optional[tuple[float, int, tuple[float, float]]] = None
        touching = False
        for j in sorted(near[k]):
            if j == own:
                continue
            d = float(lines[j].distance(p))
            if d <= _GRID_M:
                touching = True
                break
            q = lines[j].interpolate(lines[j].project(p))
            if best is None or d < best[0]:
                best = (d, j, (q.x, q.y))
        if touching:
            continue
        if best is None:
            # A ring drawn with a small gap: the line's own other end.
            ln = lines[own]
            other = Point(ln.coords[-1] if k % 2 == 0 else ln.coords[0])
            d = float(other.distance(p))
            if _GRID_M < d <= snap_m and ln.length > 4 * snap_m:
                best = (d, own, (other.x, other.y))
        if best is None:
            continue
        d, _, (qx, qy) = best
        ux, uy = (qx - p.x) / d, (qy - p.y) / d
        conn = LineString([(p.x, p.y), (qx + _OVERSHOOT_M * ux, qy + _OVERSHOOT_M * uy)])
        src = parts[own]
        out.append(_Part(conn, src.pref, src.rank, src.osm))
    return out


def build_network(
    roads_xy: list[tuple[np.ndarray, str, int]],
    popularity: dict[int, int],
    radius_m: float,
    start_radius_m: float,
    snap_m: float,
    popularity_saturation: float,
) -> Optional[Network]:
    """Noded road graph within radius_m of the origin, components near the start only."""
    disc = Point(0.0, 0.0).buffer(radius_m, quad_segs=64)
    parts: list[_Part] = []
    for xy, highway, osm_id in roads_xy:
        if len(xy) < 2:
            continue
        line = LineString(xy)
        if line.length <= _GRID_M:
            continue
        cs = class_score(highway)
        pop = max(0, int(popularity.get(osm_id, 0) or 0))
        pop_score = min(1.0, pop / popularity_saturation) if popularity_saturation > 0 else 0.0
        pref = 0.7 * cs + 0.3 * pop_score
        clipped = line.intersection(disc)
        for g in shapely.get_parts(clipped):
            if isinstance(g, LineString) and g.length > _GRID_M:
                parts.append(_Part(g, pref, cs, int(osm_id)))
    if not parts:
        return None
    parts += _gap_connectors(parts, snap_m)

    noded = shapely.union_all([p.line for p in parts], grid_size=_GRID_M)
    pieces = [g for g in shapely.get_parts(noded) if isinstance(g, LineString) and g.length > _GRID_M]
    if not pieces:
        return None

    # Which source road each piece came from: the most preferred road under its midpoint.
    src_lines = [p.line for p in parts]
    tree = shapely.STRtree(src_lines)
    mids = [pc.interpolate(0.5, normalized=True) for pc in pieces]
    pi, si = tree.query(mids, predicate="dwithin", distance=5 * _GRID_M)
    src_of: dict[int, int] = {}
    for a, b in zip(pi.tolist(), si.tolist()):
        cur = src_of.get(a)
        if cur is None or (parts[b].pref, -b) > (parts[cur].pref, -cur):
            src_of[a] = b

    node_id: dict[tuple[float, float], int] = {}
    node_xy: list[tuple[float, float]] = []

    def nid(pt) -> int:
        key = (round(pt[0], 3), round(pt[1], 3))
        n = node_id.get(key)
        if n is None:
            n = node_id[key] = len(node_xy)
            node_xy.append((float(pt[0]), float(pt[1])))
        return n

    ea, eb, coords, length, pref, rank, osm = [], [], [], [], [], [], []
    for i, pc in enumerate(pieces):
        c = np.asarray(pc.coords, dtype=float)[:, :2]
        # drop repeated points so every segment has a direction
        keep = np.concatenate([[True], np.hypot(*np.diff(c, axis=0).T) > 1e-9])
        c = c[keep]
        if len(c) < 2:
            continue
        a, b = nid(c[0]), nid(c[-1])
        if a == b and len(c) < 4:
            continue  # a closed piece needs at least a triangle
        s = src_of.get(i)
        ea.append(a)
        eb.append(b)
        coords.append(c)
        length.append(float(pc.length))
        pref.append(parts[s].pref if s is not None else 0.0)
        rank.append(parts[s].rank if s is not None else 0.0)
        osm.append(parts[s].osm if s is not None else -1)
    if not ea:
        return None
    dist0 = shapely.distance([LineString(c) for c in coords], Point(0.0, 0.0))
    near = [bool(d <= start_radius_m) for d in dist0]

    # Connected components (union-find); keep the ones with a road near the start.
    parent = list(range(len(node_xy)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in zip(ea, eb):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    keep_roots = {find(ea[e]) for e in range(len(ea)) if near[e]}
    active = [e for e in range(len(ea)) if find(ea[e]) in keep_roots]
    net = Network(node_xy, ea, eb, coords, length, pref, rank, near, osm, active, list(active))
    net.active = prune_dangles(net, active)
    return net if net.active else None


def prune_dangles(net: Network, edges: Sequence[int]) -> list[int]:
    """Drop dead ends, repeatedly: an edge at a node of degree 1 is on no cycle."""
    alive = set(edges)
    deg: Counter = Counter()
    inc: dict[int, list[int]] = defaultdict(list)
    for e in alive:
        deg[net.ea[e]] += 1
        deg[net.eb[e]] += 1
        inc[net.ea[e]].append(e)
        inc[net.eb[e]].append(e)
    stack = [v for v, d in deg.items() if d == 1]
    while stack:
        v = stack.pop()
        if deg[v] != 1:
            continue
        for e in inc[v]:
            if e in alive:
                alive.discard(e)
                for w in (net.ea[e], net.eb[e]):
                    deg[w] -= 1
                    if deg[w] == 1:
                        stack.append(w)
                break
    return sorted(alive)


# ---------------------------------------------------------------- faces


@dataclass
class Faces:
    """Faces of the planar graph from a half-edge walk.

    Half-edge h = 2e runs ea[e] -> eb[e], h = 2e + 1 the other way; each face
    lies to the left of its half-edges, so bounded faces are walked
    anticlockwise and have positive signed area.
    """

    face_of: dict[int, int]  # half-edge -> face
    bounded: list[bool]
    simple: list[bool]  # boundary walk visits no node twice
    cycle_edges: list[list[int]]  # edges in walk order (for simple faces: the boundary cycle)
    cycle_nodes: list[list[int]]  # origin node of each walk step
    odd: list[frozenset]  # edges that appear once in the walk (its boundary as a region)
    area: list[float]  # planar area, m²
    poly: list[Optional[BaseGeometry]]
    incident: dict[int, list[int]]  # node -> active edges

    def across(self, e: int, f: int) -> int:
        """The face on the other side of edge e from face f."""
        a, b = self.face_of[2 * e], self.face_of[2 * e + 1]
        return b if a == f else a


def _half_coords(net: Network, h: int) -> np.ndarray:
    c = net.coords[h >> 1]
    return c if h % 2 == 0 else c[::-1]


def build_faces(net: Network, edges: Sequence[int]) -> Faces:
    out: dict[int, list[tuple[float, int]]] = defaultdict(list)
    incident: dict[int, list[int]] = defaultdict(list)
    for e in edges:
        c = net.coords[e]
        a, b = net.ea[e], net.eb[e]
        out[a].append((math.atan2(c[1, 1] - c[0, 1], c[1, 0] - c[0, 0]), 2 * e))
        out[b].append((math.atan2(c[-2, 1] - c[-1, 1], c[-2, 0] - c[-1, 0]), 2 * e + 1))
        incident[a].append(e)
        if b != a:
            incident[b].append(e)
    order: dict[int, list[int]] = {}
    pos: dict[int, int] = {}
    for v, lst in out.items():
        lst.sort()
        order[v] = [h for _, h in lst]
        for i, h in enumerate(order[v]):
            pos[h] = i

    def dest(h: int) -> int:
        e = h >> 1
        return net.eb[e] if h % 2 == 0 else net.ea[e]

    def origin(h: int) -> int:
        e = h >> 1
        return net.ea[e] if h % 2 == 0 else net.eb[e]

    def nxt(h: int) -> int:
        # Arriving at v along h: leave by the next half-edge clockwise from h's twin.
        lst = order[dest(h)]
        return lst[pos[h ^ 1] - 1]

    face_of: dict[int, int] = {}
    bounded, simple, cyc_e, cyc_n, odd, area, poly = [], [], [], [], [], [], []
    for e in edges:
        for h0 in (2 * e, 2 * e + 1):
            if h0 in face_of:
                continue
            fid = len(bounded)
            walk = []
            h = h0
            while h not in face_of:
                face_of[h] = fid
                walk.append(h)
                h = nxt(h)
            pts = [_half_coords(net, walk[0])]
            pts += [_half_coords(net, w)[1:] for w in walk[1:]]
            ring = np.vstack(pts)
            x, y = ring[:, 0], ring[:, 1]
            signed = 0.5 * float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))
            nodes = [origin(w) for w in walk]
            es = [w >> 1 for w in walk]
            cnt = Counter(es)
            is_bounded = signed > 1e-6
            is_simple = len(set(nodes)) == len(nodes)
            g: Optional[BaseGeometry] = None
            if is_bounded:
                g = Polygon(ring)
                if not g.is_valid:
                    g = _polygonal(shapely.make_valid(g))
            bounded.append(is_bounded)
            simple.append(is_simple)
            cyc_e.append(es)
            cyc_n.append(nodes)
            odd.append(frozenset(k for k, n in cnt.items() if n % 2 == 1))
            area.append(float(g.area) if g is not None else 0.0)
            poly.append(g)
    return Faces(face_of, bounded, simple, cyc_e, cyc_n, odd, area, poly, dict(incident))


def _polygonal(geom: BaseGeometry) -> Optional[BaseGeometry]:
    polys = [g for g in shapely.get_parts(geom) if g.geom_type == "Polygon" and not g.is_empty]
    if not polys:
        # GeometryCollection: look one level down
        polys = [p for g in shapely.get_parts(geom) for p in shapely.get_parts(g)
                 if p.geom_type == "Polygon" and not p.is_empty]
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else shapely.MultiPolygon(polys)


# ---------------------------------------------------------------- coarsening


def coarsen(net: Network, faces: Faces, edges: Sequence[int], min_area: float) -> Optional[list[int]]:
    """One round of block merging for long targets, or None if nothing merges.

    Blocks smaller than min_area are merged with a neighbour by deleting the
    road pieces between them, smallest blocks first. Only two simple blocks
    whose shared border is one unbroken run are merged (two discs glued along
    one arc make a disc, so the merged block is simple too); the run with the
    least important roads is removed, then the smallest neighbour wins. Roads
    near the start are never removed, so the loop can still reach the runner.
    Each block merges at most once per round.
    """
    order = sorted((faces.area[f], f) for f in range(len(faces.bounded))
                   if faces.bounded[f] and faces.simple[f] and faces.area[f] < min_area)
    used: set[int] = set()
    drop: set[int] = set()
    for _, f in order:
        if f in used:
            continue
        es = faces.cycle_edges[f]
        k = len(es)
        best = None
        for g in sorted({faces.across(e, f) for e in es}):
            if g == f or g in used or not faces.bounded[g] or not faces.simple[g]:
                continue
            shared = [faces.across(e, f) == g for e in es]
            starts = sum(1 for i in range(k) if shared[i] and not shared[i - 1])
            if starts != 1:
                continue
            run = [es[i] for i in range(k) if shared[i]]
            if any(net.near[e] for e in run):
                continue
            key = (max(net.rank[e] for e in run), faces.area[g], g)
            if best is None or key < best[0]:
                best = (key, g, run)
        if best is None:
            continue
        _, g, run = best
        used.update((f, g))
        drop.update(run)
    if not drop:
        return None
    return prune_dangles(net, [e for e in edges if e not in drop])


# ---------------------------------------------------------------- approach legs


@dataclass
class AccessTree:
    """Shortest road paths from the road point nearest the runner.

    The source is a point part-way along edge src_edge, so both its ends are
    reached directly. dist[v] is the road distance to node v (inf when
    unreachable or beyond the cap); pred[v] is (edge, previous node), or
    (src_edge, -1) for the two ends of the source edge.
    """

    point: tuple[float, float]  # the source point, local metres
    offset_m: float  # its distance from the runner
    src_edge: int
    along: float  # metres from ea[src_edge] to the source point
    dist: list[float]
    pred: dict[int, tuple[int, int]]

    def path(self, net: Network, v: int) -> np.ndarray:
        """Road geometry from the source point to node v."""
        legs: list[np.ndarray] = []
        while True:
            e, prev = self.pred[v]
            if prev == -1:
                break
            c = net.coords[e]
            legs.append(c if net.eb[e] == v and net.ea[e] == prev else c[::-1])
            v = prev
        line = LineString(net.coords[self.src_edge])
        if v == net.ea[self.src_edge] and (net.ea[self.src_edge] != net.eb[self.src_edge]
                                           or self.along <= 0.5 * line.length):
            head = shapely.ops.substring(line, self.along, 0.0)
        else:
            head = shapely.ops.substring(line, self.along, line.length)
        h = np.asarray(head.coords, dtype=float)[:, :2] if head.geom_type == "LineString" \
            else np.array([self.point, self.point])
        parts = [h] + [c[1:] for c in reversed(legs)]
        out = np.vstack(parts)
        keep = np.concatenate([[True], np.hypot(*np.diff(out, axis=0).T) > 1e-6])
        return out[keep]


def access_tree(net: Network, cap_m: float) -> Optional[AccessTree]:
    """Dijkstra over every road piece (dead ends too) from the road point nearest the runner."""
    edges = net.full
    if not edges:
        return None
    lines = [LineString(net.coords[e]) for e in edges]
    origin = Point(0.0, 0.0)
    d = shapely.distance(lines, origin)
    k = int(np.argmin(d))
    src, line = edges[k], lines[k]
    along = float(line.project(origin))
    p = line.interpolate(along)
    adj: dict[int, list[int]] = defaultdict(list)
    for e in edges:
        adj[net.ea[e]].append(e)
        if net.eb[e] != net.ea[e]:
            adj[net.eb[e]].append(e)
    dist = [math.inf] * len(net.node_xy)
    pred: dict[int, tuple[int, int]] = {}
    heap: list[tuple[float, int]] = []
    for v, dv in ((net.ea[src], along), (net.eb[src], net.length[src] - along)):
        if dv <= cap_m and dv < dist[v]:
            dist[v] = dv
            pred[v] = (src, -1)
            heapq.heappush(heap, (dv, v))
    while heap:
        dv, v = heapq.heappop(heap)
        if dv > dist[v]:
            continue
        for e in adj[v]:
            w = net.eb[e] if net.ea[e] == v else net.ea[e]
            nd = dv + net.length[e]
            if nd <= cap_m and nd < dist[w]:
                dist[w] = nd
                pred[w] = (e, v)
                heapq.heappush(heap, (nd, w))
    return AccessTree((p.x, p.y), float(d[k]), src, along, dist, pred)
