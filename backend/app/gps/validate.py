"""Distance engine: validate fixes, split into segments, measure distance.

Checks run in order against the last accepted fix (the anchor), not the
previous raw fix:

1. invalid_coordinates: NaN, out of range, (0, 0), NaN time.
2. duplicate: same time and coordinates as an earlier fix.
3. out_of_order: time not after the last kept fix.
4. poor_accuracy: accuracy_m above max_accuracy_m. Unknown accuracy passes.
5. implausible_speed: implied speed above max_speed_mps, unless the extra
   distance is explained by the two fixes' accuracy.
6. stationary: small move from the anchor. The fix is not accepted, adds no
   distance and does not move the anchor, so slow real movement builds up
   until it passes the threshold, while drift never does. The move counts as
   small when it is under max(min_displacement_m, factor * combined accuracy),
   or when the reported speed is under stationary_speed_mps and the move is
   within twice the combined accuracy (or 2 * min_displacement_m, whichever is
   larger) plus the slowest speed times the elapsed time. The same test
   applies when the average speed since the anchor is under
   stationary_speed_mps. A phone's Doppler speed is far more reliable than its
   position, which is why it widens the test.
5b. The speed check also runs against the latest kept fix when that is a
   stationary one, since the anchor can be several seconds old.

A run of reanchor_after implausible fixes that agree with each other means
the anchor was probably the bad one. The first of them becomes a new segment
start, like a gap; the jump is counted as uncertain distance.

Gaps: a time step above long_gap_s between kept fixes starts a new segment.
The straight line across it is uncertain_distance_m and not distance_m.

Quality:
  poor: fewer than 2 accepted fixes, or rejected share (stationary excluded)
        above 40%, or uncertain distance above 30% of distance + uncertain.
  good: rejected share at most 10%, gap time at most 5% of run time, and the
        median accepted accuracy at most preferred_accuracy_m (needs at
        least one known accuracy; otherwise the run is fair at best).
  fair: everything else.
"""
from __future__ import annotations

import math
from typing import Optional

from .geodesy import distance_m, valid_coordinate
from .kalman import smooth_segment
from .track_types import (
    ALGORITHM_VERSION,
    ProcessedFix,
    RawFix,
    Segment,
    TrackConfig,
    TrackResult,
)


def _acc(f: RawFix) -> Optional[float]:
    a = f.accuracy_m
    if a is None or math.isnan(a) or a < 0:
        return None
    return a


def _acc0(f: RawFix) -> float:
    a = _acc(f)
    return 0.0 if a is None else a


class _Pipeline:
    def __init__(self, fixes: list[RawFix], cfg: TrackConfig):
        self.fixes = fixes
        self.cfg = cfg
        n = len(fixes)
        self.reasons: list[Optional[str]] = [None] * n
        self.accepted = [False] * n
        self.seg_of: list[Optional[int]] = [None] * n
        self.segs: list[list[int]] = []
        self.anchor: Optional[int] = None
        self.last_kept_t: Optional[float] = None
        self.last_kept: Optional[int] = None  # latest accepted or stationary fix
        self.pending: list[int] = []
        self.uncertain = 0.0
        self.gap_count = 0
        self.gap_time = 0.0

    # -- helpers -----------------------------------------------------------
    def _dist(self, a: int, b: int) -> float:
        fa, fb = self.fixes[a], self.fixes[b]
        return distance_m(fa.lat, fa.lng, fb.lat, fb.lng)

    def _implausible(self, a: int, b: int) -> bool:
        fa, fb = self.fixes[a], self.fixes[b]
        dt = fb.t - fa.t
        if dt <= 0:
            return True
        d = self._dist(a, b)
        cfg = self.cfg
        if d / dt <= cfg.max_speed_mps:
            return False
        return d - (_acc0(fa) + _acc0(fb)) > cfg.max_speed_mps * dt

    def _start_segment(self, i: int) -> None:
        self.segs.append([i])
        self._accept(i, len(self.segs) - 1)

    def _accept(self, i: int, seg: int) -> None:
        self.accepted[i] = True
        self.reasons[i] = None
        self.seg_of[i] = seg
        self.anchor = i
        self.last_kept = i
        self.last_kept_t = self.fixes[i].t

    def _reject(self, i: int, reason: str) -> None:
        self.accepted[i] = False
        self.reasons[i] = reason
        self.seg_of[i] = None

    # -- main loop ---------------------------------------------------------
    def run(self) -> None:
        seen: set[tuple[float, float, float]] = set()
        for i, f in enumerate(self.fixes):
            if not valid_coordinate(f.lat, f.lng) or f.t is None or math.isnan(f.t) or math.isinf(f.t):
                self._reject(i, "invalid_coordinates")
                continue
            key = (f.t, f.lat, f.lng)
            if key in seen:
                self._reject(i, "duplicate")
                continue
            seen.add(key)
            if self.last_kept_t is not None and f.t <= self.last_kept_t:
                self._reject(i, "out_of_order")
                continue
            a = _acc(f)
            if a is not None and a > self.cfg.max_accuracy_m:
                self._reject(i, "poor_accuracy")
                continue
            self._consider(i)

    def _consider(self, i: int) -> None:
        cfg = self.cfg
        f = self.fixes[i]
        if self.anchor is None:
            self._start_segment(i)
            return
        a = self.anchor
        fa = self.fixes[a]
        dt = f.t - fa.t
        d = self._dist(a, i)
        accs = _acc0(fa) + _acc0(f)

        if self._implausible(a, i) or (
            self.last_kept is not None and self.last_kept != a and self._implausible(self.last_kept, i)
        ):
            self._jump(i)
            return
        self.pending.clear()

        # stationary
        stationary = d < max(cfg.min_displacement_m, cfg.accuracy_displacement_factor * accs)
        if not stationary:
            reported_slow = (
                f.speed_mps is not None
                and not math.isnan(f.speed_mps)
                and f.speed_mps < cfg.stationary_speed_mps
            )
            average_slow = d / dt < cfg.stationary_speed_mps
            bound = max(2 * cfg.min_displacement_m, 2 * accs) + cfg.stationary_speed_mps * dt
            if (reported_slow or average_slow) and d < bound:
                stationary = True
        if stationary:
            self._reject(i, "stationary")
            self.last_kept = i
            self.last_kept_t = f.t
            return

        gap = f.t - self.last_kept_t
        if gap > cfg.long_gap_s:
            self.segs.append([])
            self.uncertain += d
            self.gap_count += 1
            self.gap_time += gap
        seg = len(self.segs) - 1
        self.segs[seg].append(i)
        self._accept(i, seg)

    def _jump(self, i: int) -> None:
        self._reject(i, "implausible_speed")
        if self.pending and not self._implausible(self.pending[-1], i):
            self.pending.append(i)
        else:
            self.pending = [i]
        if len(self.pending) < self.cfg.reanchor_after:
            return
        first, rest = self.pending[0], self.pending[1:]
        self.pending = []
        old = self.anchor
        self.uncertain += self._dist(old, first)
        self.gap_count += 1
        self.gap_time += self.fixes[first].t - (self.last_kept_t or self.fixes[first].t)
        self.segs.append([])
        self.segs[-1].append(first)
        self._accept(first, len(self.segs) - 1)
        for j in rest:
            self.reasons[j] = None
            self._consider(j)


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else 0.5 * (s[m - 1] + s[m])


def process_track(fixes: list[RawFix], config: TrackConfig | None = None) -> TrackResult:
    cfg = config or TrackConfig()
    fixes = list(fixes)
    n = len(fixes)

    # naive distance over every fix with valid coordinates, in input order
    raw = 0.0
    prev = None
    for f in fixes:
        if not valid_coordinate(f.lat, f.lng):
            continue
        if prev is not None:
            raw += distance_m(prev.lat, prev.lng, f.lat, f.lng)
        prev = f

    p = _Pipeline(fixes, cfg)
    p.run()

    filtered: dict[int, tuple[float, float]] = {}
    segments: list[Segment] = []
    distance = 0.0
    moving = 0.0
    seg_id = 0
    seg_map: dict[int, int] = {}
    for old_id, idxs in enumerate(p.segs):
        if not idxs:
            continue
        seg_map[old_id] = seg_id
        lats = [fixes[k].lat for k in idxs]
        lngs = [fixes[k].lng for k in idxs]
        ts = [fixes[k].t for k in idxs]
        if cfg.use_kalman:
            pts = smooth_segment(
                lats, lngs, ts, [_acc(fixes[k]) for k in idxs],
                cfg.kalman_accel_std, cfg.kalman_default_accuracy_m,
            )
            for k, pt in zip(idxs, pts):
                filtered[k] = pt
        else:
            pts = list(zip(lats, lngs))
        d = sum(distance_m(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:]))
        segments.append(Segment(seg_id, list(idxs), d, ts[0], ts[-1]))
        distance += d
        moving += ts[-1] - ts[0]
        seg_id += 1

    out: list[ProcessedFix] = []
    for i, f in enumerate(fixes):
        fl = filtered.get(i)
        sid = seg_map.get(p.seg_of[i]) if p.seg_of[i] is not None else None
        out.append(
            ProcessedFix(
                index=i, lat=f.lat, lng=f.lng, t=f.t,
                accepted=p.accepted[i], rejection_reason=p.reasons[i], segment_id=sid,
                filtered_lat=fl[0] if fl else None, filtered_lng=fl[1] if fl else None,
            )
        )

    accepted = sum(p.accepted)
    rejected = n - accepted
    hard_rejected = sum(1 for r in p.reasons if r is not None and r != "stationary")

    quality = _quality(fixes, p, cfg, accepted, hard_rejected, n, distance)
    return TrackResult(
        algorithm_version=ALGORITHM_VERSION,
        fixes=out,
        segments=segments,
        distance_m=distance,
        raw_distance_m=raw,
        uncertain_distance_m=p.uncertain,
        moving_time_s=moving,
        accepted_count=accepted,
        rejected_count=rejected,
        gap_count=p.gap_count,
        quality=quality,
    )


def _quality(fixes, p: _Pipeline, cfg: TrackConfig, accepted: int, hard_rejected: int, n: int, distance: float) -> str:
    rej_share = hard_rejected / n if n else 0.0
    total_uncertain = distance + p.uncertain
    if accepted < 2 or rej_share > 0.40 or (total_uncertain > 0 and p.uncertain > 0.30 * total_uncertain):
        return "poor"
    acc_idx = [i for i, ok in enumerate(p.accepted) if ok]
    run_time = fixes[acc_idx[-1]].t - fixes[acc_idx[0]].t
    gap_share = p.gap_time / run_time if run_time > 0 else 0.0
    known = [_acc(fixes[i]) for i in acc_idx if _acc(fixes[i]) is not None]
    if (
        rej_share <= 0.10
        and gap_share <= 0.05
        and known
        and _median(known) <= cfg.preferred_accuracy_m
    ):
        return "good"
    return "fair"
