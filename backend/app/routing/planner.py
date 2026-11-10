"""Route finder: suggests loops that grow the runner's territory.

Contract: docs/route-suggestions.md ("Route finder interface"). Pure Python on
shapely and pyproj; no database, no network. Helpers: graph.py (road graph,
blocks, coarsening), blocks.py (block values), search.py (beam search).

Why blocks
----------
Under the territory rules (app/gps/territory_shape.py) a closed loop earns the
land it encloses. A loop that follows roads and does not cross itself is the
boundary of a set of city blocks (the bounded faces of the planar road graph),
and the land it earns is exactly the land of those blocks. So instead of
searching over paths, which is exponential and mostly yields loops that cross
themselves, we search over sets of blocks, grown one neighbour at a time, and
read the loop off as the set's boundary.

1. Graph (graph.py). All coordinates go into an azimuthal equidistant frame
   centred on the runner, as territory_shape does. Roads are clipped to the
   search disc, radius min(target x 0.5, 3000 m) (a loop of length L that
   passes near the start cannot reach further than about L/2). OSM gaps are
   closed: a road end that stops within ``snap_m`` (5 m) of another road gets
   a short connector to it. ``union_all`` on a 1 cm grid nodes everything, so
   roads meet only at nodes and the graph is planar (a bridge over a road
   becomes a junction; see limitations). Each piece keeps the class and
   osm_id of the road under it. Only connected components with a road within
   ``start_radius_m`` of the runner are kept. Blocks use the graph with dead
   ends pruned (an edge at a degree-1 node is on no cycle); approach legs use
   all of it, dead ends included, since a runner often starts on one (a
   campus or hostel service road).

2. Blocks. A half-edge walk (at each node, leave by the next edge clockwise)
   gives every face with the face on its left: bounded faces have positive
   signed area, the outer face of each component negative. Each edge knows
   the face on each side, so adjacency and boundaries are exact, not
   geometric guesses. A face whose walk visits a node twice (a road loop
   hanging inside a block on a single link) is marked "not simple".

   Long targets in dense streets would need hundreds of blocks per loop, so
   the graph is coarsened first when needed: while blocks are smaller than
   half of (target/4)² / ``blocks_per_loop``, small blocks are merged with a
   neighbour by dropping the least important roads between them. Roads near
   the start are never dropped. Loops still follow real roads; they just use
   fewer of the minor ones.

3. Block values (blocks.py). Each block is cut by the territory layers: the
   runner's land (weight 0), each followed friend's land (weight
   ``steal_weight``, 1.5) and the rest (weight 1). Friends' layers are made
   disjoint from the runner's and from each other (in user_id order), so no
   square metre counts twice. Anyone else's land is not an input at all, so
   it counts as new land, as the doc says. Areas are planar in the local
   frame: within 3 km of its centre the aeqd area scale differs from 1 by
   less than 1e-7, far below anything that matters here. Reported numbers
   come from the verification step, which is geodesic.

   Section focus: the plane is cut into squares of ``section_size_m`` (250 m),
   the runner at the centre of one. A section where the runner holds between
   5% and 60% gets ``section_bonus`` (x1.15) on the value of the land inside
   it, so loops lean towards growing ground the runner has started on. It
   multiplies value, never creates it: a block already all theirs is still 0.

4. Search (search.py). A state is a set S of blocks whose boundary (edges
   with exactly one side in S) is one simple cycle, i.e. S is a disc: no hole
   (a second cycle) and no pinch point (a node of boundary degree 4). Then
   the boundary is a loop that encloses exactly S. Adding a simple block f to
   a disc S gives a disc iff the part of f's border on S's boundary is one
   unbroken run of edges and no other node of f lies on S's boundary; this is
   checked locally in O(edges of f). Blocks that are not simple use a full
   check of the new boundary.

   Approach leg. If some boundary edge is within ``start_radius_m`` of the
   runner the loop passes them and the leg is 0, as before. Otherwise the
   route runs from the road point nearest the runner (which must itself be
   within ``start_radius_m``) along the shortest road path to the nearest
   boundary node, round the loop and back the same way. One Dijkstra from
   that point gives road distances to every node, so a state's leg is the
   least distance over its boundary nodes; the state keeps that node and
   rescans its boundary only when a new block swallows it. The leg is at most
   min(``max_access_fraction`` x target, ``max_access_m``) one way, and the
   total, loop + 2 x leg, must be within +-25% of the target. The territory
   rules award such a route the loop's land plus the leg's 3 m strip (an
   out-and-back tail encloses nothing).

   Seeds are all blocks the runner can reach: the loop passes near them or
   the leg is within its cap. Each level adds one block
   to each state of the beam; duplicates (same set by another order) are
   found with Zobrist hashes before any set is built. The next beam takes the
   top states by three keys: score, new-land value and friends'-land value
   (``beam_width`` in all, at most half of each key's share from one seed, so
   the beam does not collapse onto one direction). Each key is a projected
   value, value x ((hi - 2 x leg) / loop length)²: a disc keeps value /
   length² as it grows, so this is roughly what the state would hold when
   its loop uses all the length the leg leaves. Compact states and short legs
   win. Every state whose total length is within +-25% of the target joins
   a pool, as do the best in-window children by each key and by closeness
   to the target.

   Score = value of the blocks + ``road_weight_sq_m_per_m`` x sum over the
   loop of (metres x road preference). Preference is 0..1: 0.7 x class
   (trunk 1 ... service 0) + 0.3 x friend popularity (saturating at 3 runs).
   At 0.02 m² per metre a 2.5 km loop gains at most 50 m², so roads only decide
   between loops whose land is within that of each other. Each metre of leg
   run (out and back) costs ``access_penalty_sq_m_per_m`` (1 m²): legs earn
   only a thin strip, so of two loops with the same land the nearer wins.

   Work bounds (deterministic first): ``max_loop_blocks`` levels,
   ``max_evaluations`` candidate checks, then ``max_search_s`` wall-clock as a
   last resort. Then at most ``max_verifications`` loops are verified.

5. Verification. For a pooled set the loop is its boundary, walked with the
   set on the left (anticlockwise), along the real road geometry, starting at
   the point of the loop nearest the runner, or with a leg: out from the
   road point nearest the runner, round the loop from the leg's end node, and
   back. It must be within the distance
   window (geodesic length) and start within ``start_radius_m``. Then
   ``build_territory_shape([route])`` must say "loop", and new / stolen (per
   friend) / already-mine areas are geodesic areas of that shape intersected
   with the layers. Block sums only choose what to verify.

6. Results. Up to three loops with different labels whose enclosed areas
   overlap by at most ``max_overlap`` (intersection over union):
   "Most from friends" (most land taken), "Most new land", "Closest to your
   usual run" (distance nearest the target, any gain). Loops within 1% of the
   best on the label's measure count as equal and the higher score wins.
   Each needs at least ``min_gain_sq_m`` of the land it is named for. They
   are returned by score, best first; [] when there is no usable loop.

Limitations: roads crossing on bridges or in tunnels are treated as
junctions; a loop never repeats a road or touches itself, so figure-8s and
lollipops are not suggested; beam search is a heuristic and can miss the
best loop on large maps; one-way streets are ignored (it is a run).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import shapely
from pyproj import Geod
from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry

from app.gps.geodesy import valid_coordinate
from app.gps.territory_shape import ShapeConfig, _geodesic_area, build_territory_shape

from .blocks import section_multipliers, value_blocks
from .graph import AccessTree, Faces, LocalFrame, Network, access_tree, build_faces, build_network, coarsen
from .search import BlockSearch, SearchLimits, State

_GEOD = Geod(ellps="WGS84")

LABEL_FRIENDS = "Most from friends"
LABEL_NEW = "Most new land"
LABEL_CLOSEST = "Closest to your usual run"
LABEL_OTHER = "Another option"


# ---------------------------------------------------------------- interface


@dataclass
class RoadWay:
    osm_id: int
    highway: str
    points: list[tuple[float, float]]  # (lat, lng)


@dataclass
class OwnedArea:
    user_id: int
    geometry: BaseGeometry  # Polygon | MultiPolygon, WGS-84, x=lng y=lat


@dataclass
class PlannerInput:
    start: tuple[float, float]  # (lat, lng)
    roads: list[RoadWay]
    my_user_id: int
    my_territory: Optional[OwnedArea]
    friend_territories: list[OwnedArea]  # people the runner follows only
    target_distance_m: float
    popularity: dict[int, int] = field(default_factory=dict)  # osm_id -> friends' runs on it


@dataclass
class PlannerConfig:
    steal_weight: float = 1.5  # value of a friend's m² against an empty m²
    start_radius_m: float = 150.0  # the loop must pass this close to the runner
    distance_tolerance: float = 0.25  # accepted length: target x (1 +- this)
    search_radius_factor: float = 0.5  # roads within target x this of the start ...
    max_search_radius_m: float = 3000.0  # ... capped here
    section_size_m: float = 250.0
    section_min_share: float = 0.05  # runner's share of a section for the bonus
    section_max_share: float = 0.60
    section_bonus: float = 1.15
    road_weight_sq_m_per_m: float = 0.02  # road preference, m² of score per metre at preference 1
    popularity_saturation: float = 3.0  # friends' runs on a road for full popularity
    snap_m: float = 5.0  # close OSM gaps up to this
    blocks_per_loop: float = 30.0  # coarsen until a loop of the target length needs about this many blocks
    max_coarsen_rounds: int = 8
    beam_width: int = 24
    max_loop_blocks: int = 150  # search levels
    max_evaluations: int = 60_000  # candidate block additions checked
    max_search_s: float = 1.0  # wall-clock cap on the search (last resort)
    max_verifications: int = 30
    max_overlap: float = 0.4  # max intersection-over-union of two suggestions' areas
    min_gain_sq_m: float = 200.0  # least land a suggestion must win for its label
    max_suggestions: int = 3
    max_access_fraction: float = 0.35  # approach leg (one way) at most this x the target ...
    max_access_m: float = 1500.0  # ... and at most this
    access_penalty_sq_m_per_m: float = 1.0  # score lost per metre of leg run (out and back)
    shape: ShapeConfig = field(default_factory=ShapeConfig)


@dataclass
class Suggestion:
    route: list[tuple[float, float]]  # closed route along roads (leg out, loop, leg back), (lat, lng), first == last
    distance_m: float
    enclosed: BaseGeometry
    new_area_sq_m: float
    stolen_area_sq_m: float
    stolen_by_user: dict[int, float]
    already_mine_sq_m: float
    gain_sq_m: float
    score: float
    label: str
    reason: str
    approach_m: float = 0.0  # one-way road leg from the runner to the loop (0: the loop passes them)


# ---------------------------------------------------------------- territory layers


def _polygonal(geom: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    polys = []
    stack = [geom]
    while stack:
        g = stack.pop()
        if g.is_empty:
            continue
        if g.geom_type == "Polygon":
            polys.append(g)
        elif hasattr(g, "geoms"):
            stack.extend(g.geoms)
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else shapely.MultiPolygon(polys)


def _garea(geom: Optional[BaseGeometry]) -> float:
    g = _polygonal(geom)
    return _geodesic_area(g) if g is not None else 0.0


@dataclass
class _Layers:
    mine_ll: Optional[BaseGeometry]
    friends_ll: dict[int, BaseGeometry]  # disjoint from mine and each other
    mine_xy: Optional[BaseGeometry]
    friends_xy: list[BaseGeometry]


def _layers(inp: PlannerInput, frame: LocalFrame, radius_m: float) -> _Layers:
    # Clip in lng/lat to a box round the search disc, then make the layers disjoint.
    r = radius_m + 100.0
    ring = [(r * math.cos(a), r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)]
    sq = [(-r, -r), (r, -r), (r, r), (-r, r)]
    ll = frame.to_latlng(np.array(ring + sq))
    lats, lngs = [p[0] for p in ll], [p[1] for p in ll]
    clip = box(min(lngs), min(lats), max(lngs), max(lats))

    def prep(g: Optional[BaseGeometry]) -> Optional[BaseGeometry]:
        g = _polygonal(g)
        if g is None:
            return None
        return _polygonal(g.intersection(clip))

    mine = prep(inp.my_territory.geometry) if inp.my_territory is not None else None
    by_user: dict[int, list[BaseGeometry]] = {}
    for fa in inp.friend_territories or []:
        if fa is None or fa.user_id == inp.my_user_id:
            continue
        g = prep(fa.geometry)
        if g is not None:
            by_user.setdefault(int(fa.user_id), []).append(g)
    friends: dict[int, BaseGeometry] = {}
    taken = mine
    for uid in sorted(by_user):
        g = _polygonal(shapely.union_all(by_user[uid]))
        if g is not None and taken is not None:
            g = _polygonal(g.difference(taken))
        if g is None:
            continue
        friends[uid] = g
        taken = g if taken is None else _polygonal(shapely.union(taken, g))

    def to_xy(g):
        return _polygonal(frame.geom_to_xy(g)) if g is not None else None

    fx = [to_xy(g) for g in friends.values()]
    return _Layers(mine, friends, to_xy(mine), [g for g in fx if g is not None])


# ---------------------------------------------------------------- loops


def _ring(net: Network, fc: Faces, s: State) -> np.ndarray:
    """The boundary of s as a closed ring, anticlockwise (s on the left)."""
    inc: dict[int, list[int]] = {}
    for e in s.boundary:
        inc.setdefault(net.ea[e], []).append(e)
        inc.setdefault(net.eb[e], []).append(e)

    def oriented(e: int, at: Optional[int]) -> tuple[np.ndarray, int]:
        fwd = fc.face_of[2 * e] in s.faces
        if at is not None and net.ea[e] != net.eb[e]:
            fwd = net.ea[e] == at
        c = net.coords[e] if fwd else net.coords[e][::-1]
        return c, (net.eb[e] if fwd else net.ea[e])

    first = min(s.boundary)
    c, v = oriented(first, None)
    pts = [c]
    e = first
    while True:
        a, b = inc[v]
        e2 = b if a == e else a
        if e2 == first:
            break
        c, v = oriented(e2, v)
        pts.append(c[1:])
        e = e2
    ring = np.vstack(pts)
    ring[-1] = ring[0]
    return ring


def _rotate_to_nearest(ring: np.ndarray, x: float = 0.0, y: float = 0.0) -> np.ndarray:
    """The same closed ring, starting and ending at its point nearest (x, y)."""
    line = LineString(ring)
    d = line.project(Point(x, y))
    seg = np.hypot(*np.diff(ring, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    i = int(np.searchsorted(cum, d, side="right") - 1)
    i = min(max(i, 0), len(ring) - 2)
    t = 0.0 if seg[i] <= 0 else (d - cum[i]) / seg[i]
    p = ring[i] + t * (ring[i + 1] - ring[i])
    body = np.vstack([[p], ring[i + 1:-1], ring[: i + 1], [p]])
    keep = np.concatenate([[True], np.hypot(*np.diff(body, axis=0).T) > 1e-6])
    body = body[keep]
    body[-1] = p
    return body


def _bearing_word(x: float, y: float) -> str:
    names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    az = math.degrees(math.atan2(x, y)) % 360.0
    return names[int((az + 22.5) // 45) % 8]


def _fmt_area(a: float) -> str:
    step = 100 if a >= 1000 else 10
    return f"{round(a / step) * step:,.0f} m²"


def _reason(n_blocks: int, centroid: tuple[float, float], new: float, stolen: float,
            leg: float = 0.0) -> str:
    cx, cy = centroid
    blocks = f"{n_blocks} block" + ("" if n_blocks == 1 else "s")
    where = "around you" if math.hypot(cx, cy) < 50.0 else f"{_bearing_word(cx, cy)} of you"
    if leg >= 10.0:
        where += f", {round(leg / 10) * 10:,.0f} m away by road"
    parts = []
    if new >= 1.0:
        parts.append(f"{_fmt_area(new)} new")
    if stolen >= 1.0:
        parts.append(f"{_fmt_area(stolen)} from friends")
    gain = " and ".join(parts) if parts else "no new land"
    return f"Loops {blocks} {where}; {gain}"


@dataclass
class _Checked:
    state: State
    suggestion: Optional[Suggestion]


class _Verifier:
    def __init__(self, inp: PlannerInput, cfg: PlannerConfig, frame: LocalFrame, net: Network,
                 fc: Faces, layers: _Layers, lo: float, hi: float, tree: AccessTree):
        self.inp, self.cfg, self.frame, self.net, self.fc = inp, cfg, frame, net, fc
        self.tree = tree
        self.layers, self.lo, self.hi = layers, lo, hi
        self.cache: dict[int, Optional[Suggestion]] = {}
        self.count = 0

    def __call__(self, s: State) -> Optional[Suggestion]:
        if s.z in self.cache:
            return self.cache[s.z]
        if self.count >= self.cfg.max_verifications:
            return None
        self.count += 1
        out = self._verify(s)
        self.cache[s.z] = out
        return out

    def _verify(self, s: State) -> Optional[Suggestion]:
        cfg, inp = self.cfg, self.inp
        leg = s.leg
        try:
            ring = _ring(self.net, self.fc, s)
            if leg > 0:
                # Out along the roads to the loop, round it, and back the same way.
                out = self.tree.path(self.net, s.leg_node)
                loop = _rotate_to_nearest(ring, *out[-1])
                loop[0] = loop[-1] = out[-1]
                ring = np.vstack([out, loop[1:], out[::-1][1:]])
            else:
                ring = _rotate_to_nearest(ring)
        except (KeyError, ValueError):
            return None
        route = self.frame.to_latlng(ring)
        route[-1] = route[0]
        lats, lngs = [p[0] for p in route], [p[1] for p in route]
        dist = float(_GEOD.line_length(lngs, lats))
        if not (self.lo - 1e-6 <= dist <= self.hi + 1e-6):
            return None
        _, _, d0 = _GEOD.inv(inp.start[1], inp.start[0], route[0][1], route[0][0])
        if d0 > cfg.start_radius_m + 0.5:
            return None
        shape = build_territory_shape([route], 0.0, cfg.shape)
        if shape.kind != "loop" or shape.geometry is None:
            return None
        g = shape.geometry
        total = shape.area_sq_m
        L = self.layers
        mine = _garea(g.intersection(L.mine_ll)) if L.mine_ll is not None else 0.0
        by_user = {}
        for uid, fg in L.friends_ll.items():
            a = _garea(g.intersection(fg))
            if a > 0:
                by_user[uid] = a
        stolen = sum(by_user.values())
        new = max(0.0, total - mine - stolen)
        c = _polygonal(self.frame.geom_to_xy(g)).centroid
        return Suggestion(
            route=route, distance_m=dist, enclosed=g, new_area_sq_m=new, stolen_area_sq_m=stolen,
            stolen_by_user=by_user, already_mine_sq_m=mine, gain_sq_m=new + stolen,
            score=s.score, label="",
            reason=_reason(len(s.faces), (c.x, c.y), new, stolen, leg), approach_m=leg,
        )


# ---------------------------------------------------------------- entry point


def _iou(a: State, b: State, area: list[float]) -> float:
    inter = sum(area[f] for f in a.faces & b.faces)
    if inter <= 0:
        return 0.0
    ua = sum(area[f] for f in a.faces)
    ub = sum(area[f] for f in b.faces)
    return inter / max(1e-9, ua + ub - inter)


def plan_routes(inp: PlannerInput, config: Optional[PlannerConfig] = None) -> list[Suggestion]:
    """Up to config.max_suggestions loops, best first; [] if the roads near the start form none."""
    cfg = config or PlannerConfig()
    if inp is None or not inp.roads or not inp.start or not valid_coordinate(*inp.start):
        return []
    target = float(inp.target_distance_m or 0.0)
    if not math.isfinite(target) or target <= 0:
        return []
    lo, hi = target * (1 - cfg.distance_tolerance), target * (1 + cfg.distance_tolerance)
    radius = min(target * cfg.search_radius_factor, cfg.max_search_radius_m)
    if radius <= 0:
        return []
    frame = LocalFrame(*inp.start)

    # Roads into the local frame, in one transform.
    ok_roads = []
    for r in inp.roads:
        pts = [(float(a), float(b)) for a, b in (r.points or []) if valid_coordinate(a, b)]
        if len(pts) >= 2:
            ok_roads.append((r, pts))
    if not ok_roads:
        return []
    flat = [p for _, pts in ok_roads for p in pts]
    xy = frame.to_xy(flat)
    roads_xy, k = [], 0
    for r, pts in ok_roads:
        roads_xy.append((xy[k:k + len(pts)], r.highway, int(r.osm_id)))
        k += len(pts)

    net = build_network(roads_xy, inp.popularity or {}, radius, cfg.start_radius_m,
                        cfg.snap_m, cfg.popularity_saturation)
    if net is None:
        return []
    edges = net.active
    fc = build_faces(net, edges)
    min_block = 0.5 * (target / 4.0) ** 2 / max(1.0, cfg.blocks_per_loop)
    for _ in range(cfg.max_coarsen_rounds):
        nxt = coarsen(net, fc, edges, min_block)
        if nxt is None or not nxt:
            break
        edges = nxt
        fc = build_faces(net, edges)
    if not any(fc.bounded):
        return []
    # Road distances from the road point nearest the runner, for approach legs.
    max_leg = max(0.0, min(cfg.max_access_fraction * target, cfg.max_access_m))
    tree = access_tree(net, max_leg)
    if tree is None or tree.offset_m > cfg.start_radius_m:
        return []

    layers = _layers(inp, frame, radius)
    sections, size = section_multipliers(layers.mine_xy, radius, cfg.section_size_m,
                                         cfg.section_min_share, cfg.section_max_share, cfg.section_bonus)
    vals = value_blocks(fc.poly, layers.mine_xy, layers.friends_xy, cfg.steal_weight, sections, size)

    search = BlockSearch(net, fc, vals.value, vals.new_value, vals.stolen_value, lo, hi,
                         cfg.road_weight_sq_m_per_m, tree.dist, max_leg, cfg.access_penalty_sq_m_per_m)
    res = search.run(SearchLimits(cfg.beam_width, cfg.max_loop_blocks, cfg.max_evaluations, cfg.max_search_s))
    if not res.pool:
        return []

    area = fc.area
    est_new = vals.new.tolist()
    est_stolen = vals.stolen.tolist()

    def est(s: State, arr) -> float:
        return sum(arr[f] for f in s.faces)

    verify = _Verifier(inp, cfg, frame, net, fc, layers, lo, hi, tree)
    chosen: list[tuple[State, Suggestion]] = []
    per_label = max(1, cfg.max_verifications // 3)

    def pick(label: str, rank_key, measure, eligible) -> None:
        if len(chosen) >= cfg.max_suggestions:
            return
        ranked = sorted(res.pool, key=rank_key, reverse=True)
        found: list[tuple[State, Suggestion]] = []
        tried = 0
        for s in ranked:
            if tried >= per_label:
                break
            if any(_iou(s, c, area) > cfg.max_overlap for c, _ in chosen):
                continue
            tried += 1
            sug = verify(s)
            if sug is not None and eligible(sug):
                found.append((s, sug))
        if not found:
            return
        best = max(measure(g) for _, g in found)
        tol = 0.01 * max(abs(best), 1.0)
        near_best = [(s, g) for s, g in found if measure(g) >= best - tol]
        s, g = max(near_best, key=lambda sg: sg[1].score)
        g = Suggestion(**{**g.__dict__, "label": label})
        chosen.append((s, g))

    m = cfg.min_gain_sq_m
    pick(LABEL_FRIENDS,
         lambda s: (est(s, est_stolen), s.score),
         lambda g: g.stolen_area_sq_m,
         lambda g: g.stolen_area_sq_m >= m)
    pick(LABEL_NEW,
         lambda s: (est(s, est_new), s.score),
         lambda g: g.new_area_sq_m,
         lambda g: g.new_area_sq_m >= m)
    pick(LABEL_CLOSEST,
         lambda s: (-abs(s.total - target), s.score),
         lambda g: -abs(g.distance_m - target),
         lambda g: g.gain_sq_m >= m)
    out = [g for _, g in chosen]
    out.sort(key=lambda g: -g.score)
    return _honest_labels(out, target)


def _honest_labels(out: list[Suggestion], target: float) -> list[Suggestion]:
    """Relabel so every label is true among the suggestions shown.

    Suggestions are picked one label at a time while keeping them different,
    so a later pick can carry "Most new land" while an earlier one has more.
    Each label goes to the suggestion that really leads on it; one that leads
    on nothing is "Another option".
    """
    labels: dict[int, str] = {}
    left = set(range(len(out)))

    def give(label: str, key, ok) -> None:
        cands = [i for i in left if ok(out[i])]
        if not cands:
            return
        i = max(cands, key=key)
        # Only if it leads among ALL suggestions, not just the unlabelled ones.
        if all(key(i) >= key(j) for j in range(len(out))):
            labels[i] = label
            left.discard(i)

    give(LABEL_FRIENDS, lambda i: out[i].stolen_area_sq_m, lambda g: g.stolen_area_sq_m > 0)
    give(LABEL_NEW, lambda i: out[i].new_area_sq_m, lambda g: g.new_area_sq_m > 0)
    give(LABEL_CLOSEST, lambda i: -abs(out[i].distance_m - target), lambda g: True)
    return [
        Suggestion(**{**g.__dict__, "label": labels.get(i, LABEL_OTHER)})
        for i, g in enumerate(out)
    ]
