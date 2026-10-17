"""
Setup script: enable PostGIS, create tables, and upgrade old databases in place.

Usage:
    python setup_postgis.py

Safe to run on every start. There is no migration tool, so new columns on
existing tables are added here with ALTER TABLE ... ADD COLUMN IF NOT EXISTS.

Prerequisites:
    - PostgreSQL with PostGIS extension installed.
    - The 'terrarun' database already exists.
"""

from sqlalchemy import text
from app.database import engine, Base

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401
from app.models import RUN_ADDED_COLUMNS


def setup_database(bind=engine) -> None:
    """Idempotent: enable PostGIS, create missing tables, add missing columns."""
    with bind.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

    # Adds missing tables (users, runs, gps_fixes, ...). Never alters existing ones.
    Base.metadata.create_all(bind=bind)

    with bind.begin() as conn:
        for name, sql_type in RUN_ADDED_COLUMNS:
            conn.execute(text(f"ALTER TABLE runs ADD COLUMN IF NOT EXISTS {name} {sql_type};"))
        # Same name as the constraint create_all makes on a fresh database,
        # so this is a no-op there. NULL client_run_id values never collide.
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_user_client_run_id "
            "ON runs (user_id, client_run_id);"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_gps_fixes_run_id ON gps_fixes (run_id);"
        ))
        # Older versions measured area in Web Mercator, which inflates it away
        # from the equator. Recompute stored areas in true square metres.
        conn.execute(text(
            "UPDATE territories SET area_sq_m = ST_Area(geom::geography) "
            "WHERE ABS(area_sq_m - ST_Area(geom::geography)) > 0.01;"
        ))


def main():
    print("[1/2] Enabling PostGIS, syncing tables and columns …")
    setup_database()
    print("      ✓ Database schema up to date")

    print("[2/2] Verifying PostGIS version …")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT PostGIS_Full_Version();")).scalar()
    print(f"      ✓ {version}")

    print("\nDone!  Your database is ready for territory capture.")


if __name__ == "__main__":
    main()
