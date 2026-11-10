"""Beam search over sets of city blocks (see planner.py for the design).

A state is a set S of bounded faces whose boundary is one simple cycle (S is
a topological disc). The boundary is kept as the set of edges with exactly one
side in S: adding a face toggles its edges (symmetric difference), so length,
road preference and the near-start count update in O(edges of the face).

Approach leg: when no boundary edge is within start_radius of the runner,
the route runs out along the roads to the boundary node nearest by road
(``leg_dist``, from one Dijkstra), round the loop, and back. The state keeps
that node; it changes only when the new block brings a nearer node, or when
the block swallows the node (then the boundary is rescanned).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .graph import Faces, Network

_OVERSHOOT = 1.5  # states longer than this x the longest accepted route are dropped


@dataclass
class State:
    faces: frozenset
    boundary: frozenset
    z: int  # Zobrist hash of faces
    length: float  # the loop alone
    road: float  # sum of length x preference over the boundary
    near: int  # boundary edges within start_radius of the runner
    leg_dist: float  # road distance from the runner's road point to leg_node
    leg_node: int  # boundary node nearest the runner by road (-1: none reachable)
    value: float
    new_value: float
    stolen_value: float
    seed: int
    score: float = 0.0

    @property
    def leg(self) -> float:
        """One-way approach leg: 0 when the loop itself passes near the runner."""
        return 0.0 if self.near > 0 else self.leg_dist

    @property
    def total(self) -> float:
        return self.length + 2.0 * self.leg


@dataclass
class SearchLimits:
    beam_width: int
    max_blocks: int
    max_evaluations: int
    max_seconds: float


@dataclass
class SearchResult:
    pool: list[State]  # states whose total length is in the accepted window
    evaluations: int
    levels: int
    timed_out: bool


def is_simple_cycle(net: Network, boundary: frozenset) -> bool:
    """True if the edges form exactly one simple cycle (every node degree 2, connected)."""
    if not boundary:
        return False
    adj: dict[int, list[int]] = {}
    for e in boundary:
        adj.setdefault(net.ea[e], []).append(e)
        adj.setdefault(net.eb[e], []).append(e)
    if any(len(v) != 2 for v in adj.values()):
        return False
    start = next(iter(boundary))
    seen = {start}
    v = net.eb[start]
    prev = start
    while True:
        a, b = adj[v]
        e = b if a == prev else a
        if e == start:
            break
        if e in seen:
            return False
        seen.add(e)
        v = net.eb[e] if net.ea[e] == v else net.ea[e]
        prev = e
    return len(seen) == len(boundary)


class BlockSearch:
    def __init__(self, net: Network, faces: Faces, value: np.ndarray, new_value: np.ndarray,
                 stolen_value: np.ndarray, lo: float, hi: float, road_weight: float,
                 node_dist: list[float], max_leg: float, leg_weight: float):
        self.net, self.fc = net, faces
        self.value = value.tolist()
        self.new_value = new_value.tolist()
        self.stolen_value = stolen_value.tolist()
        self.lo, self.hi = lo, hi
        self.target = 0.5 * (lo + hi)
        self.rw = road_weight
        self.dist = node_dist
        self.max_leg = max_leg
        self.lw = leg_weight
        rng = np.random.default_rng(20261110)
        self.zob = [int(x) for x in rng.integers(1, 2 ** 62, size=len(faces.bounded))]
        self.len = net.length
        self.lp = [l * p for l, p in zip(net.length, net.pref)]
        self.near = net.near

    # -- helpers

    def _on_boundary(self, v: int, B: frozenset) -> bool:
        return any(e in B for e in self.fc.incident.get(v, ()))

    def _nearest(self, nodes, best=(math.inf, -1)) -> tuple[float, int]:
        d = self.dist
        for v in nodes:
            c = (d[v], v)
            if c < best:
                best = c
        return best

    def _boundary_nodes(self, B) -> set[int]:
        net = self.net
        return {net.ea[e] for e in B} | {net.eb[e] for e in B}

    def _ok(self, length: float, near: int, leg_dist: float) -> bool:
        leg = 0.0 if near > 0 else leg_dist
        return leg <= self.max_leg and length + 2 * leg <= _OVERSHOOT * self.hi

    def _score(self, value: float, road: float, near: int, leg_dist: float) -> float:
        leg = 0.0 if near > 0 else leg_dist
        return value + self.rw * road - self.lw * 2.0 * leg

    # -- one step

    def child(self, s: State, f: int) -> Optional[tuple]:
        """Metrics of S + f if it is still a disc the runner can reach, else None.

        For a simple face f the test is local: S + f is a disc iff the part of
        f's boundary cycle that lies on S's boundary is one unbroken run of
        edges (not none, not all), and no other node of f touches S's
        boundary (that would be a pinch point). Two discs glued along one arc
        make a disc; a second contact makes a hole or a pinch. Faces whose own
        walk is not simple (a bridge or an inner ring inside them) use the
        full check on the toggled boundary.
        """
        fc, B = self.fc, s.boundary
        if fc.simple[f]:
            es = fc.cycle_edges[f]
            k = len(es)
            shared = [e in B for e in es]
            starts = 0
            for i in range(k):
                if shared[i] and not shared[i - 1]:
                    starts += 1
            if starts != 1:
                return None
            nodes = fc.cycle_nodes[f]
            removed = set()
            kept = []
            for i in range(k):
                if shared[i - 1] and shared[i]:
                    removed.add(nodes[i])  # inside the shared run: no longer on the boundary
                    continue
                kept.append(nodes[i])
                if not shared[i] and not shared[i - 1] and self._on_boundary(nodes[i], B):
                    return None
            toggles = es
            if s.leg_node in removed:
                leg = self._nearest(kept, self._nearest(self._boundary_nodes(B) - removed))
            else:
                leg = self._nearest(kept, (s.leg_dist, s.leg_node))
        else:
            toggles = fc.odd[f]
            if not any(e in B for e in toggles):
                return None
            nb = B ^ toggles
            if not is_simple_cycle(self.net, nb):
                return None
            leg = self._nearest(self._boundary_nodes(nb))
        dl = dr = 0.0
        dn = 0
        for e in toggles:
            sg = -1 if e in B else 1
            dl += sg * self.len[e]
            dr += sg * self.lp[e]
            if self.near[e]:
                dn += sg
        near = s.near + dn
        length = s.length + dl
        if not self._ok(length, near, leg[0]):
            return None
        return (length, s.road + dr, near, leg[0], leg[1])

    def make(self, s: State, f: int, m: tuple) -> State:
        toggles = frozenset(self.fc.cycle_edges[f]) if self.fc.simple[f] else self.fc.odd[f]
        value = s.value + self.value[f]
        return State(
            faces=s.faces | {f}, boundary=s.boundary ^ toggles, z=s.z ^ self.zob[f],
            length=m[0], road=m[1], near=m[2], leg_dist=m[3], leg_node=m[4],
            value=value, new_value=s.new_value + self.new_value[f],
            stolen_value=s.stolen_value + self.stolen_value[f], seed=s.seed,
            score=self._score(value, m[1], m[2], m[3]),
        )

    def seeds(self) -> list[State]:
        """Every block the runner can reach: its loop passes near them, or a leg gets there."""
        out = []
        fc = self.fc
        for f in range(len(fc.bounded)):
            if not fc.bounded[f]:
                continue
            B = fc.odd[f]
            near = sum(1 for e in B if self.near[e])
            length = sum(self.len[e] for e in B)
            leg = self._nearest(self._boundary_nodes(B))
            if not self._ok(length, near, leg[0]):
                continue
            if not fc.simple[f] and not is_simple_cycle(self.net, B):
                continue
            road = sum(self.lp[e] for e in B)
            out.append(State(
                faces=frozenset([f]), boundary=B, z=self.zob[f], length=length,
                road=road, near=near, leg_dist=leg[0], leg_node=leg[1], value=self.value[f],
                new_value=self.new_value[f], stolen_value=self.stolen_value[f], seed=f,
                score=self._score(self.value[f], road, near, leg[0]),
            ))
        return out

    # -- beam

    def _in_window(self, total: float) -> bool:
        return self.lo <= total <= self.hi

    def run(self, lim: SearchLimits) -> SearchResult:
        t0 = time.perf_counter()
        rw, hi = self.rw, self.hi

        # Rank by projected value, not value: states of one level hold the
        # same number of blocks, and the compact one with the same land can
        # still grow much further before its route is too long. If the land
        # ahead is like the land so far, a disc keeps value / length² as it
        # grows, so value x (room / length)² is the value it would reach when
        # its loop uses all the room left: hi minus the leg there and back.
        def proj(v: float, m: tuple) -> float:
            leg = 0.0 if m[2] > 0 else m[3]
            room = hi - 2.0 * leg
            return v * (room / m[0]) ** 2 if room > 0 else -math.inf

        keys = (
            lambda c: proj(c[0].value + c[4] + rw * c[3][1], c[3]),  # score
            lambda c: proj(c[0].new_value + c[5] + rw * c[3][1], c[3]),  # new land
            lambda c: proj(c[0].stolen_value + c[6] + rw * c[3][1], c[3]),  # friends' land
        )
        per_key = max(1, math.ceil(lim.beam_width / len(keys)))
        per_seed = max(1, math.ceil(per_key / 2))

        beam = self.seeds()
        pool: dict[int, State] = {}
        for s in beam:
            if self._in_window(s.total):
                pool[s.z] = s
        evals, levels, timed_out = 0, 0, False
        # Keep the best seeds only, by the same rule as later levels.
        beam = self._select(
            [(s, None, s.z, (s.length, s.road, s.near, s.leg_dist, s.leg_node), 0.0, 0.0, 0.0)
             for s in beam],
            keys, per_key, per_seed, pool, materialize=False)
        while beam and levels < lim.max_blocks:
            levels += 1
            children: dict[int, tuple] = {}
            for s in beam:
                nb = set()
                for e in s.boundary:
                    a, b = self.fc.face_of[2 * e], self.fc.face_of[2 * e + 1]
                    g = b if a in s.faces else a
                    if g not in s.faces and self.fc.bounded[g]:
                        nb.add(g)
                for f in sorted(nb):
                    z = s.z ^ self.zob[f]
                    if z in children:
                        continue
                    evals += 1
                    m = self.child(s, f)
                    if m is not None:
                        children[z] = (s, f, z, m, self.value[f], self.new_value[f], self.stolen_value[f])
                if evals >= lim.max_evaluations or time.perf_counter() - t0 > lim.max_seconds:
                    timed_out = True
                    break
            if not children:
                break
            beam = self._select(list(children.values()), keys, per_key, per_seed, pool, materialize=True)
            if timed_out:
                break
        return SearchResult(list(pool.values()), evals, levels, timed_out)

    @staticmethod
    def _total(m: tuple) -> float:
        return m[0] + 2.0 * (0.0 if m[2] > 0 else m[3])

    def _select(self, cands: list[tuple], keys, per_key: int, per_seed: int,
                pool: dict[int, State], materialize: bool) -> list[State]:
        """Next beam: the top per_key states by each key, at most per_seed per seed block.

        Also adds to the pool every chosen state in the length window, and the
        best in-window state by each key and by closeness to the target, so
        good routes that the beam passes over are not lost.
        """
        def mat(c) -> State:
            if not materialize:
                return c[0]
            got = pool.get(c[2])
            return got if got is not None else self.make(c[0], c[1], c[3])

        chosen: dict[int, tuple] = {}
        for key in keys:
            ranked = sorted(cands, key=key, reverse=True)  # stable: ties keep generation order
            taken, by_seed = 0, {}
            for c in ranked:
                if taken >= per_key:
                    break
                sd = c[0].seed
                if by_seed.get(sd, 0) >= per_seed:
                    continue
                by_seed[sd] = by_seed.get(sd, 0) + 1
                taken += 1
                chosen.setdefault(c[2], c)
        inwin = [c for c in cands if self._in_window(self._total(c[3]))]
        extra = []
        if inwin:
            for key in keys:
                extra.append(max(inwin, key=key))
            extra.append(min(inwin, key=lambda c: abs(self._total(c[3]) - self.target)))
        out = []
        for c in chosen.values():
            s = mat(c)
            out.append(s)
            if self._in_window(s.total):
                pool[s.z] = s
        for c in extra:
            if c[2] not in pool:
                pool[c[2]] = mat(c)
        return out
