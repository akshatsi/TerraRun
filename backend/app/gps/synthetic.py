"""Deterministic synthetic GPS tracks for tests and benchmarks.

Every generator takes a seed and returns (fixes, reference_distance_m), where
the reference is the true path length covered by the samples.

Noise model: position error is Gaussian in metres, converted to degrees with
a geodesic offset. Real receiver error drifts slowly, so most of it is an
AR(1) process (correlation 0.95 per second) plus a small white part. noise_m
is the RMS horizontal error (radial). accuracy_m is reported near that level.
Reported speed is the true speed plus noise.
"""
from __future__ import annotations

import bisect
import math
import random
from dataclasses import replace

from .geodesy import offset_point
from .track_types import RawFix

ORIGIN_LAT = 26.9342
ORIGIN_LNG = 75.9241
T0 = 1_760_000_000.0

_RHO = 0.95  # per-second correlation of the slow error
_WHITE_SHARE = 0.05  # share of error variance that is white


class _Noise:
    def __init__(self, rng: random.Random, noise_m: float, hz: float):
        self.rng = rng
        self.sigma = noise_m / math.sqrt(2.0)  # per axis
        self.rho = _RHO ** (1.0 / hz)
        s = self.sigma * math.sqrt(1.0 - _WHITE_SHARE)
        self.slow_sigma = s
        self.white_sigma = self.sigma * math.sqrt(_WHITE_SHARE)
        self.ex = rng.gauss(0, s)
        self.ey = rng.gauss(0, s)

    def step(self) -> tuple[float, float]:
        r, s = self.rho, self.slow_sigma
        k = math.sqrt(1.0 - r * r) * s
        self.ex = r * self.ex + self.rng.gauss(0, k)
        self.ey = r * self.ey + self.rng.gauss(0, k)
        return (
            self.ex + self.rng.gauss(0, self.white_sigma),
            self.ey + self.rng.gauss(0, self.white_sigma),
        )


def _densify(points: list[tuple[float, float]], step: float = 0.25):
    """Dense polyline plus cumulative lengths."""
    xs, ys, cum = [points[0][0]], [points[0][1]], [0.0]
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        seg = math.hypot(x2 - x1, y2 - y1)
        k = max(1, int(math.ceil(seg / step)))
        for j in range(1, k + 1):
            f = j / k
            xs.append(x1 + (x2 - x1) * f)
            ys.append(y1 + (y2 - y1) * f)
            total += seg / k
            cum.append(total)
    return xs, ys, cum


def _at(xs, ys, cum, s: float, wrap: bool):
    total = cum[-1]
    if wrap:
        s = s % total
    s = min(s, total)
    j = bisect.bisect_right(cum, s) - 1
    j = min(j, len(cum) - 2)
    span = cum[j + 1] - cum[j]
    f = (s - cum[j]) / span if span > 0 else 0.0
    x = xs[j] + (xs[j + 1] - xs[j]) * f
    y = ys[j] + (ys[j + 1] - ys[j]) * f
    heading = math.degrees(math.atan2(xs[j + 1] - xs[j], ys[j + 1] - ys[j])) % 360
    return x, y, heading


def _build(
    rng: random.Random, truth: list[tuple[float, float, float]], noise_m: float, hz: float,
    speed_mps: float, accuracy_fn=None,
) -> list[RawFix]:
    noise = _Noise(rng, noise_m, hz)
    fixes: list[RawFix] = []
    for k, (x, y, hd) in enumerate(truth):
        ex, ey = noise.step()
        lat, lng = offset_point(ORIGIN_LAT, ORIGIN_LNG, x + ex, y + ey)
        acc = noise_m * rng.uniform(0.9, 1.3) if accuracy_fn is None else accuracy_fn(k)
        fixes.append(
            RawFix(
                lat=lat, lng=lng, t=T0 + k / hz, accuracy_m=acc,
                speed_mps=max(0.0, speed_mps + rng.gauss(0, 0.2)),
                heading_deg=hd, altitude_m=431.0 + rng.gauss(0, 1.0),
            )
        )
    return fixes


def _sample_path(points, total_s_fn, speed_mps, hz, wrap=False, length=None):
    xs, ys, cum = _densify(points)
    total = length if length is not None else cum[-1]
    n = int(total / (speed_mps / hz)) + 1
    truth = [_at(xs, ys, cum, k * speed_mps / hz, wrap) for k in range(n)]
    return truth, (n - 1) * speed_mps / hz


def track_400m_loop(seed: int, noise_m: float = 4.0, hz: float = 1.0, speed_mps: float = 3.5,
                    laps: int = 3) -> tuple[list[RawFix], float]:
    """400 m running track: two straights and two semicircles."""
    r = 36.0
    straight = (400.0 - 2 * math.pi * r) / 2
    pts: list[tuple[float, float]] = []
    h = straight / 2
    pts.append((-h, -r))
    pts.append((h, -r))
    for a in range(1, 180):  # right semicircle, bottom to top
        th = -math.pi / 2 + math.pi * a / 180
        pts.append((h + r * math.cos(th), r * math.sin(th)))
    pts.append((h, r))
    pts.append((-h, r))
    for a in range(1, 180):  # left semicircle, top to bottom
        th = math.pi / 2 + math.pi * a / 180
        pts.append((-h + r * math.cos(th), r * math.sin(th)))
    pts.append((-h, -r))
    xs, ys, cum = _densify(pts)
    perim = cum[-1]
    rng = random.Random(seed)
    n = int(laps * perim / (speed_mps / hz)) + 1
    truth = [_at(xs, ys, cum, k * speed_mps / hz, True) for k in range(n)]
    return _build(rng, truth, noise_m, hz, speed_mps), (n - 1) * speed_mps / hz


def route_sharp_turns_1km(seed: int, noise_m: float = 3.0, hz: float = 1.0,
                          speed_mps: float = 3.0) -> tuple[list[RawFix], float]:
    """Staircase route of 100 m legs with 90 degree turns, 1 km in all."""
    pts = [(0.0, 0.0)]
    for k in range(10):
        x, y = pts[-1]
        pts.append((x + 100.0, y) if k % 2 == 0 else (x, y + 100.0))
    rng = random.Random(seed)
    truth, ref = _sample_path(pts, None, speed_mps, hz)
    return _build(rng, truth, noise_m, hz, speed_mps), ref


def urban_multipath_detail(seed: int, noise_m: float = 4.0, hz: float = 1.0, speed_mps: float = 3.2,
                           distance_m: float = 4000.0):
    """Like urban_multipath, plus the set of outlier fix indices."""
    rng = random.Random(seed)
    pts = [(0.0, 0.0)]
    heading = rng.choice([0, 90, 180, 270])
    total = 0.0
    while total < distance_m + 50:
        leg = rng.uniform(120, 300)
        total += leg
        x, y = pts[-1]
        pts.append((x + leg * math.sin(math.radians(heading)), y + leg * math.cos(math.radians(heading))))
        heading = (heading + rng.choice([90, -90])) % 360
    xs, ys, cum = _densify(pts)
    n = int(distance_m / (speed_mps / hz)) + 1
    truth = [_at(xs, ys, cum, k * speed_mps / hz, False) for k in range(n)]
    ref = (n - 1) * speed_mps / hz

    # plan outliers
    outliers: dict[int, tuple[float, float, float]] = {}  # index -> (dx, dy, accuracy)
    k = 10
    while k < n - 10:
        if rng.random() < 0.015:
            length = 1 if rng.random() < 0.6 else rng.randint(2, 4)
            flagged = rng.random() < 0.85  # receiver reported poor accuracy
            mag = rng.uniform(20, 80) if flagged else rng.uniform(45, 80)
            ang = rng.uniform(0, 2 * math.pi)
            for j in range(length):
                m = mag + rng.uniform(-3, 3)
                a = ang + rng.uniform(-0.1, 0.1)
                acc = rng.uniform(22, 60) if flagged else rng.uniform(12, 19)
                outliers[k + j] = (m * math.sin(a), m * math.cos(a), acc)
            k += length + 8
        else:
            k += 1

    base_noise = _Noise(rng, noise_m, hz)
    fixes: list[RawFix] = []
    for i, (x, y, hd) in enumerate(truth):
        ex, ey = base_noise.step()
        if i in outliers:
            ox, oy, acc = outliers[i]
            ex, ey = ex + ox, ey + oy
        else:
            acc = noise_m * rng.uniform(0.9, 1.3)
        lat, lng = offset_point(ORIGIN_LAT, ORIGIN_LNG, x + ex, y + ey)
        fixes.append(RawFix(lat, lng, T0 + i / hz, acc, max(0.0, speed_mps + rng.gauss(0, 0.2)), hd,
                            431.0 + rng.gauss(0, 1.0)))
    return fixes, ref, set(outliers)


def urban_multipath(seed: int, noise_m: float = 4.0, hz: float = 1.0, speed_mps: float = 3.2,
                    distance_m: float = 4000.0) -> tuple[list[RawFix], float]:
    """3-5 km city route with multipath outliers of 20-80 m, singly or in bursts of 2-4."""
    fixes, ref, _ = urban_multipath_detail(seed, noise_m, hz, speed_mps, distance_m)
    return fixes, ref


def stationary(seed: int, minutes: float = 10.0, noise_m: float = 5.0, hz: float = 1.0
               ) -> tuple[list[RawFix], float]:
    """Phone lying still; the position jitters."""
    rng = random.Random(seed)
    n = int(minutes * 60 * hz)
    truth = [(0.0, 0.0, 0.0)] * n
    fixes = _build(rng, truth, noise_m, hz, 0.0)
    fixes = [replace(f, speed_mps=abs(rng.gauss(0, 0.15))) for f in fixes]
    return fixes, 0.0


def with_gap(fixes: list[RawFix], start_index: int, seconds: float) -> list[RawFix]:
    """Drop the fixes in the time window starting at fixes[start_index]."""
    t0 = fixes[start_index].t
    return [f for f in fixes if not (t0 <= f.t < t0 + seconds)]


def with_duplicates(fixes: list[RawFix], ratio: float, seed: int = 0) -> list[RawFix]:
    """Repeat a random share of fixes right after the original."""
    rng = random.Random(seed)
    out: list[RawFix] = []
    for f in fixes:
        out.append(f)
        if rng.random() < ratio:
            out.append(replace(f))
    return out


def with_poor_accuracy(fixes: list[RawFix], ratio: float, seed: int = 0) -> list[RawFix]:
    """Degrade a random share: accuracy 30-80 m and a matching position error."""
    rng = random.Random(seed)
    out: list[RawFix] = []
    for f in fixes:
        if rng.random() < ratio:
            acc = rng.uniform(30, 80)
            ang = rng.uniform(0, 2 * math.pi)
            mag = acc * rng.uniform(0.3, 0.8)
            lat, lng = offset_point(f.lat, f.lng, mag * math.sin(ang), mag * math.cos(ang))
            out.append(replace(f, lat=lat, lng=lng, accuracy_m=acc))
        else:
            out.append(f)
    return out
