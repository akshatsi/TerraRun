"""
Territory response schemas.
"""

import uuid

from pydantic import BaseModel


class TerritoryResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    color: str
    area_m2: float
    polygon_geojson: dict | None = None  # GeoJSON geometry


class TerritoryMapResponse(BaseModel):
    """All territories within a bounding box."""
    territories: list[TerritoryResponse]
