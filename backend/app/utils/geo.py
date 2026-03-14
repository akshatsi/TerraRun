"""
Geospatial utility helpers using Shapely.
"""

from shapely.geometry import LineString, MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union


def buffer_linestring(coords: list[tuple[float, float]], buffer_m: float = 0.00015) -> dict:
    """
    Take a list of (lng, lat) coords, create a LINESTRING, and buffer it
    to produce a thin polygon representing the 'strip' the runner covered.

    buffer_m ≈ 0.00015 degrees ≈ ~15 metres at the equator.
    For production, convert to a projected CRS for metre‑accurate buffering.

    Returns a GeoJSON dict of the resulting Polygon.
    """
    if len(coords) < 2:
        return None
    line = LineString(coords)
    polygon = line.buffer(buffer_m, cap_style="round", join_style="round")
    return mapping(polygon)


def union_polygons(geojson_a: dict | None, geojson_b: dict | None) -> dict | None:
    """Union two GeoJSON geometries into a single MultiPolygon."""
    shapes = []
    if geojson_a:
        shapes.append(shape(geojson_a))
    if geojson_b:
        shapes.append(shape(geojson_b))

    if not shapes:
        return None

    merged = unary_union(shapes)

    # Ensure we always store as MultiPolygon
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])

    return mapping(merged)


def subtract_polygon(base_geojson: dict | None, subtract_geojson: dict) -> dict | None:
    """
    Remove the subtract_geojson area from base_geojson.
    Used for overlap resolution — new runner 'takes' territory from old runner.
    """
    if base_geojson is None:
        return None

    base = shape(base_geojson)
    to_remove = shape(subtract_geojson)
    result = base.difference(to_remove)

    if result.is_empty:
        return None

    if isinstance(result, Polygon):
        result = MultiPolygon([result])

    return mapping(result)


def calculate_area_m2(geojson: dict | None) -> float:
    """
    Calculate area in square metres (approximate).
    For production, reproject to a local UTM zone for better accuracy.
    1 degree ≈ 111,320 m at the equator.
    """
    if geojson is None:
        return 0.0
    geom = shape(geojson)
    # Rough conversion: area in sq‑degrees × (111320)²
    return geom.area * (111_320 ** 2)


def coords_to_linestring_wkt(coords: list[tuple[float, float]]) -> str:
    """Convert [(lng, lat), ...] to WKT LINESTRING for PostGIS."""
    if len(coords) < 2:
        return None
    line = LineString(coords)
    return line.wkt
