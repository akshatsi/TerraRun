"""
Run model — stores individual run sessions with GPS tracks and metrics.
"""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Timestamps ──
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Computed metrics ──
    distance_m: Mapped[float] = mapped_column(Float, default=0.0)
    duration_s: Mapped[int] = mapped_column(Integer, default=0)
    avg_pace: Mapped[float | None] = mapped_column(Float, nullable=True)  # min/km

    # ── Route geometry (LINESTRING in EPSG:4326) ──
    polyline: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), default="active"  # active | paused | completed
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # ── Relationships ──
    user = relationship("User", back_populates="runs")
    gps_points = relationship("GpsPoint", back_populates="run", lazy="selectin", order_by="GpsPoint.timestamp")

    def __repr__(self) -> str:
        return f"<Run {self.id} user={self.user_id} dist={self.distance_m}m>"


class GpsPoint(Base):
    """Raw GPS point recorded during a live run."""
    __tablename__ = "gps_points"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # ── Relationships ──
    run = relationship("Run", back_populates="gps_points")

    def __repr__(self) -> str:
        return f"<GpsPoint ({self.lat}, {self.lng}) @ {self.timestamp}>"
