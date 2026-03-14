"""
Territory service — convert run routes into territory polygons.

Overlap rule (v1): LAST‑WRITE‑WINS
When a new run overlaps another user's territory, the overlapping strip is
removed from the previous owner and added to the new runner.
"""

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Polygon, shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.territory import Territory
from app.models.user import User
from app.utils.geo import buffer_linestring, calculate_area_m2, subtract_polygon, union_polygons


async def update_territory_after_run(
    db: AsyncSession,
    user_id,
    gps_coords: list[tuple[float, float]],
) -> Territory:
    """
    Main entry point called after a run is saved.
    1. Buffer the run's GPS route into a thin polygon strip.
    2. Union it with the user's existing territory.
    3. For all OTHER users whose territory overlaps, subtract the new strip (last‑write‑wins).
    4. Recalculate areas.
    """
    # ── Step 1: Buffer the route ──
    new_strip = buffer_linestring(gps_coords)
    if new_strip is None:
        # Not enough points to form a strip — return existing territory
        result = await db.execute(
            select(Territory).where(Territory.user_id == user_id)
        )
        return result.scalar_one_or_none()

    # ── Step 2: Get or create user's territory ──
    result = await db.execute(
        select(Territory).where(Territory.user_id == user_id)
    )
    territory = result.scalar_one_or_none()

    if territory is None:
        territory = Territory(user_id=user_id)
        db.add(territory)
        await db.flush()

    # Convert existing polygon to GeoJSON
    existing_geojson = None
    if territory.polygon is not None:
        existing_shape = to_shape(territory.polygon)
        from shapely.geometry import mapping
        existing_geojson = mapping(existing_shape)

    # Union with new strip
    merged = union_polygons(existing_geojson, new_strip)
    if merged:
        merged_shape = shape(merged)
        if isinstance(merged_shape, Polygon):
            merged_shape = MultiPolygon([merged_shape])
        territory.polygon = from_shape(merged_shape, srid=4326)
        territory.area_m2 = calculate_area_m2(merged)
    else:
        territory.area_m2 = 0.0

    # ── Step 3: Subtract from other users (last‑write‑wins) ──
    other_result = await db.execute(
        select(Territory).where(Territory.user_id != user_id)
    )
    other_territories = other_result.scalars().all()

    for other in other_territories:
        if other.polygon is None:
            continue

        other_shape = to_shape(other.polygon)
        from shapely.geometry import mapping as shp_mapping
        other_geojson = shp_mapping(other_shape)

        subtracted = subtract_polygon(other_geojson, new_strip)
        if subtracted:
            sub_shape = shape(subtracted)
            if isinstance(sub_shape, Polygon):
                sub_shape = MultiPolygon([sub_shape])
            other.polygon = from_shape(sub_shape, srid=4326)
            other.area_m2 = calculate_area_m2(subtracted)
        else:
            other.polygon = None
            other.area_m2 = 0.0

        # Update the other user's cached area
        other_user_result = await db.execute(
            select(User).where(User.id == other.user_id)
        )
        other_user = other_user_result.scalar_one_or_none()
        if other_user:
            other_user.territory_area_m2 = other.area_m2

    # ── Step 4: Update current user's cached area ──
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.territory_area_m2 = territory.area_m2

    await db.flush()
    await db.refresh(territory)
    return territory
