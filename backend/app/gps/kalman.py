"""Constant-velocity Kalman filter in a local metric projection.

State per axis is [position, velocity]. East and north are independent and
share the same covariance, so each axis runs a 2-state filter. The filter is
forward only and is reset for every segment. It is off by default: smoothing
can shorten real curves, so benchmark before trusting it.
"""
from __future__ import annotations

from typing import Sequence

from pyproj import CRS, Transformer


def _run_axis(zs: Sequence[float], ts: Sequence[float], rs: Sequence[float], q: float) -> list[float]:
    p, v = zs[0], 0.0
    p00, p01, p11 = rs[0], 0.0, 25.0  # velocity sigma 5 m/s at start
    out = [p]
    q2 = q * q
    for k in range(1, len(zs)):
        dt = ts[k] - ts[k - 1]
        # predict
        p += v * dt
        p00 = p00 + 2 * dt * p01 + dt * dt * p11 + q2 * dt ** 4 / 4
        p01 = p01 + dt * p11 + q2 * dt ** 3 / 2
        p11 = p11 + q2 * dt * dt
        # update
        s = p00 + rs[k]
        k0, k1 = p00 / s, p01 / s
        y = zs[k] - p
        p += k0 * y
        v += k1 * y
        p00, p01, p11 = p00 - k0 * p00, p01 - k0 * p01, p11 - k1 * p01
        out.append(p)
    return out


def smooth_segment(
    lats: Sequence[float],
    lngs: Sequence[float],
    ts: Sequence[float],
    accuracies: Sequence[float | None],
    accel_std: float,
    default_accuracy_m: float,
) -> list[tuple[float, float]]:
    """Return filtered (lat, lng) for one segment."""
    n = len(lats)
    if n < 2:
        return list(zip(lats, lngs))
    crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lats[0]} +lon_0={lngs[0]} +datum=WGS84 +units=m +no_defs"
    )
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    xs, ys = fwd.transform(list(lngs), list(lats))
    rs = [(a if a and a > 0 else default_accuracy_m) ** 2 for a in accuracies]
    fx = _run_axis(xs, ts, rs, accel_std)
    fy = _run_axis(ys, ts, rs, accel_std)
    lon_o, lat_o = inv.transform(fx, fy)
    return [(float(la), float(lo)) for la, lo in zip(lat_o, lon_o)]
