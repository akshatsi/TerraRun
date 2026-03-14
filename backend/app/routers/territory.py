"""
Territory routes — fetch user territory and map view.
"""

from fastapi import APIRouter, Depends, Query
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.territory import Territory
from app.models.user import User
from app.schemas.territory import TerritoryMapResponse, TerritoryResponse
from app.utils.dependencies import get_current_user

router = APIRouter(prefix="/territory", tags=["territory"])


def _territory_to_response(territory: Territory, username: str) -> TerritoryResponse:
    """Convert a Territory ORM object to a response schema."""
    geojson = None
    if territory.polygon is not None:
        geojson = mapping(to_shape(territory.polygon))
    return TerritoryResponse(
        user_id=territory.user_id,
        username=username,
        color=territory.color,
        area_m2=territory.area_m2,
        polygon_geojson=geojson,
    )


@router.get("/me", response_model=TerritoryResponse)
async def get_my_territory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current user's territory polygon."""
    result = await db.execute(
        select(Territory).where(Territory.user_id == current_user.id)
    )
    territory = result.scalar_one_or_none()

    if territory is None:
        return TerritoryResponse(
            user_id=current_user.id,
            username=current_user.username,
            color="#00ff88",
            area_m2=0.0,
            polygon_geojson=None,
        )

    return _territory_to_response(territory, current_user.username)


@router.get("/map", response_model=TerritoryMapResponse)
async def get_territory_map(
    min_lat: float = Query(..., ge=-90, le=90),
    min_lng: float = Query(..., ge=-180, le=180),
    max_lat: float = Query(..., ge=-90, le=90),
    max_lng: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all territories within a bounding box for map rendering.
    Uses PostGIS ST_Intersects with an envelope.
    """
    from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope

    bbox = ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)

    query = (
        select(Territory, User.username)
        .join(User, Territory.user_id == User.id)
        .where(ST_Intersects(Territory.polygon, bbox))
    )
    result = await db.execute(query)
    rows = result.all()

    territories = []
    for territory, username in rows:
        territories.append(_territory_to_response(territory, username))

    return TerritoryMapResponse(territories=territories)
