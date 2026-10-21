"""Per-km splits, elevation gain and top speed from accepted GPS fixes.

Pure functions, no database. Input fixes must be in recorded order. Fixes in
different segments are never joined: the distance and the time between two
segments (a gap) count for nothing, so a split's duration is moving time.

Elevation: altitudes are smoothed with a centred 5-point moving average, then
gain adds a rise only once it exceeds the last counted level by 1 m (so jitter
under 1 m adds nothing). Split elevation change is the difference of smoothed
altitude at the split's two ends.

Top speed: the largest reported speed among the fixes; if none report speed,
the largest fix-to-fix speed over a window of at least 5 s inside a segment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .geodesy import distance_m

SPLIT_M = 1000.0
MIN_PARTIAL_M = 1.0
ALT_NOISE_M = 1.0
ALT_WINDOW = 5
SPEED_WINDOW_S = 5.0


@dataclass(frozen=True)
class TrackPoint:
    lat: float
    lng: float
    t: float                       # seconds
    segment: int = 0
    altitude_m: Optional[float] = None
    speed_mps: Optional[float] = None


@dataclass(frozen=True)
class Split:
    km: int
    distance_m: float
    duration_s: float
    elevation_change_m: Optional[float]

    @property
    def pace_s_per_km(self) -> int:
        return round(self.duration_s / (self.distance_m / 1000.0))


def smooth_altitudes(points: Sequence[TrackPoint]) -> list[Optional[float]]:
    """Centred moving average over fixes that have an altitude; None elsewhere."""
    idx = [i for i, p in enumerate(points) if p.altitude_m is not None]
    out: list[Optional[float]] = [None] * len(points)
    half = ALT_WINDOW // 2
    vals = [points[i].altitude_m for i in idx]
    for k, i in enumerate(idx):
        win = vals[max(0, k - half): k + half + 1]
        out[i] = sum(win) / len(win)
    return out


def elevation_gain_m(points: Sequence[TrackPoint]) -> Optional[float]:
    alts = [a for a in smooth_altitudes(points) if a is not None]
    if not alts:
        return None
    ref, gain = alts[0], 0.0
    for a in alts[1:]:
        if a - ref >= ALT_NOISE_M:
            gain += a - ref
            ref = a
        elif ref - a >= ALT_NOISE_M:
            ref = a
    return round(gain, 1)


def max_speed_kmh(points: Sequence[TrackPoint]) -> Optional[float]:
    reported = [p.speed_mps for p in points if p.speed_mps is not None and p.speed_mps >= 0]
    if reported:
        return round(max(reported) * 3.6, 1)
    best: Optional[float] = None
    for i, p in enumerate(points):
        for q in points[i + 1:]:
            if q.segment != p.segment:
                break
            if q.t - p.t >= SPEED_WINDOW_S:
                v = distance_m(p.lat, p.lng, q.lat, q.lng) / (q.t - p.t)
                best = v if best is None else max(best, v)
                break
    return None if best is None else round(best * 3.6, 1)


def compute_splits(points: Sequence[TrackPoint]) -> list[Split]:
    """One split per full km, then a final partial split."""
    if len(points) < 2:
        return []
    alts = smooth_altitudes(points)

    def alt_at(i: int, j: int, frac: float) -> Optional[float]:
        a, b = alts[i], alts[j]
        if a is None or b is None:
            return b if frac >= 0.5 and b is not None else a
        return a + (b - a) * frac

    splits: list[Split] = []
    cum = 0.0                 # metres travelled inside segments
    moving = 0.0              # seconds spent moving inside segments
    next_b = SPLIT_M
    start_cum, start_moving = 0.0, 0.0
    start_alt = next((a for a in alts if a is not None), None)
    last_alt = start_alt

    def change(end_alt):
        if start_alt is None or end_alt is None:
            return None
        return round(end_alt - start_alt, 1)

    for i in range(len(points) - 1):
        p, q = points[i], points[i + 1]
        if p.segment != q.segment:
            continue
        leg = distance_m(p.lat, p.lng, q.lat, q.lng)
        dt = max(q.t - p.t, 0.0)
        while leg > 0 and cum + leg >= next_b:
            frac = (next_b - cum) / leg
            t_moving = moving + dt * frac
            end_alt = alt_at(i, i + 1, frac)
            splits.append(Split(
                km=len(splits) + 1, distance_m=SPLIT_M,
                duration_s=t_moving - start_moving,
                elevation_change_m=change(end_alt),
            ))
            start_cum, start_moving, start_alt = next_b, t_moving, end_alt
            next_b += SPLIT_M
        cum += leg
        moving += dt
        if alts[i + 1] is not None:
            last_alt = alts[i + 1]

    rest = cum - start_cum
    if rest >= MIN_PARTIAL_M and moving - start_moving > 0:
        splits.append(Split(
            km=len(splits) + 1, distance_m=rest,
            duration_s=moving - start_moving, elevation_change_m=change(last_alt),
        ))
    return splits
