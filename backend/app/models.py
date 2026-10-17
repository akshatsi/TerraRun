from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime, Boolean, BigInteger,
    UniqueConstraint, Text,
)
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)


# Columns added after the first release. setup_postgis.py adds each one to an
# existing runs table with ALTER TABLE ... ADD COLUMN IF NOT EXISTS, so keep
# this list in step with the Run model below: (name, SQL type).
RUN_ADDED_COLUMNS = [
    ("client_run_id", "VARCHAR(64)"),
    ("started_at", "TIMESTAMP WITH TIME ZONE"),
    ("ended_at", "TIMESTAMP WITH TIME ZONE"),
    ("raw_distance_km", "DOUBLE PRECISION"),
    ("client_distance_km", "DOUBLE PRECISION"),
    ("uncertain_distance_m", "DOUBLE PRECISION"),
    ("moving_time_s", "DOUBLE PRECISION"),
    ("accepted_fix_count", "INTEGER"),
    ("rejected_fix_count", "INTEGER"),
    ("gap_count", "INTEGER"),
    ("quality", "VARCHAR(16)"),
    ("algorithm_version", "VARCHAR(32)"),
    ("status", "VARCHAR(16)"),
    ("processed_at", "TIMESTAMP WITH TIME ZONE"),
    ("processed_route_geom", "geometry(MULTILINESTRING,4326)"),
    ("observed_corridor_geom", "geometry(GEOMETRY,4326)"),
    ("awarded_geom", "geometry(GEOMETRY,4326)"),
    ("observed_area_sq_m", "DOUBLE PRECISION"),
    ("awarded_area_sq_m", "DOUBLE PRECISION"),
    ("territory_kind", "TEXT"),
]


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("user_id", "client_run_id", name="uq_runs_user_client_run_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    distance_km = Column(Float, nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    avg_speed = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Raw route exactly as received.
    route_geom = Column(
        Geometry("LINESTRING", srid=4326, spatial_index=True),
        nullable=True,
    )

    # --- Server-side processing (see docs/gps-accuracy.md) ---
    client_run_id = Column(String(64), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    raw_distance_km = Column(Float, nullable=True)
    client_distance_km = Column(Float, nullable=True)
    uncertain_distance_m = Column(Float, nullable=True)
    moving_time_s = Column(Float, nullable=True)
    accepted_fix_count = Column(Integer, nullable=True)
    rejected_fix_count = Column(Integer, nullable=True)
    gap_count = Column(Integer, nullable=True)
    quality = Column(String(16), nullable=True)
    algorithm_version = Column(String(32), nullable=True)
    status = Column(String(16), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processed_route_geom = Column(
        Geometry("MULTILINESTRING", srid=4326, spatial_index=False), nullable=True
    )
    observed_corridor_geom = Column(
        Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=True
    )
    awarded_geom = Column(
        Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=True
    )
    observed_area_sq_m = Column(Float, nullable=True)
    awarded_area_sq_m = Column(Float, nullable=True)
    # "loop" | "route" | "none"; see docs/gps-accuracy.md section 4.
    territory_kind = Column(Text, nullable=True)


class GpsFix(Base):
    __tablename__ = "gps_fixes"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=True)
    horizontal_accuracy_m = Column(Float, nullable=True)
    reported_speed_mps = Column(Float, nullable=True)
    heading_deg = Column(Float, nullable=True)
    altitude_m = Column(Float, nullable=True)
    accepted = Column(Boolean, nullable=False, default=False)
    rejection_reason = Column(String(32), nullable=True)
    segment_id = Column(Integer, nullable=True)


class Territory(Base):
    """Each user has at most one territory polygon, grown/shrunk by runs."""
    __tablename__ = "territories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    geom = Column(
        Geometry("GEOMETRY", srid=4326, spatial_index=True),
        nullable=False,
    )
    area_sq_m = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
