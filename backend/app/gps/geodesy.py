"""Geodesic helpers on the WGS-84 ellipsoid. Never planar degrees."""
from __future__ import annotations

import math
from typing import Iterable, Sequence

from pyproj import Geod

_GEOD = Geod(ellps="WGS84")


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Geodesic distance in metres between two points."""
    _, _, d = _GEOD.inv(lng1, lat1, lng2, lat2)
    return float(d)


def path_length_m(points: Sequence[tuple[float, float]]) -> float:
    """Sum of geodesic legs over (lat, lng) points."""
    total = 0.0
    for (la1, ln1), (la2, ln2) in zip(points, points[1:]):
        total += distance_m(la1, ln1, la2, ln2)
    return total


def offset_point(lat: float, lng: float, east_m: float, north_m: float) -> tuple[float, float]:
    """Move a point by metres east and north. Returns (lat, lng)."""
    dist = math.hypot(east_m, north_m)
    if dist == 0.0:
        return lat, lng
    az = math.degrees(math.atan2(east_m, north_m))
    lng2, lat2, _ = _GEOD.fwd(lng, lat, az, dist)
    return float(lat2), float(lng2)


def valid_coordinate(lat: float, lng: float) -> bool:
    """False for NaN, out of range values and the (0, 0) null island."""
    if lat is None or lng is None:
        return False
    if math.isnan(lat) or math.isnan(lng) or math.isinf(lat) or math.isinf(lng):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return False
    if lat == 0.0 and lng == 0.0:
        return False
    return True
