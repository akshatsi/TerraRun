"""
Territory model — stores user‑owned polygons on the map.
Each user has ONE row whose polygon is a MULTIPOLYGON that grows with every run.
"""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Territory(Base):
    __tablename__ = "territories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── PostGIS MULTIPOLYGON (EPSG:4326) ──
    # Represents ALL territory owned by the user as a single multi‑polygon.
    polygon: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )

    # ── Cached area in square metres ──
    area_m2: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Territory color for map rendering ──
    color: Mapped[str] = mapped_column(
        default="#00ff88"  # neon green default
    )

    last_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ──
    user = relationship("User", back_populates="territory")

    def __repr__(self) -> str:
        return f"<Territory user={self.user_id} area={self.area_m2}m²>"
