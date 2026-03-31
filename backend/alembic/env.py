"""
Alembic env.py — configured for async SQLAlchemy + PostGIS.
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure the backend root (/app) is on sys.path so 'app' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import Base

# Import ALL models so they are registered with Base.metadata
from app.models.user import User  # noqa: F401
from app.models.run import Run, GpsPoint  # noqa: F401
from app.models.territory import Territory  # noqa: F401
from app.models.badge import Badge  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


IGNORE_TABLES = {
    "spatial_ref_sys", "topology", "layer", "loader_lookuptables",
    "loader_platform", "loader_variables", "pagc_gaz", "pagc_lex",
    "pagc_rules", "geocode_settings", "geocode_settings_default",
    "direction_lookup", "secondary_unit_lookup", "state_lookup",
    "street_type_lookup", "county_lookup", "countysub_lookup",
    "place_lookup", "zip_lookup", "zip_lookup_all", "zip_lookup_base",
    "zip_state", "zip_state_loc", "state", "county", "tract", "bg",
    "zcta5", "faces", "featnames", "edges", "addrfeat", "addr",
    "cousub", "place", "tabblock", "tabblock20"
}

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in IGNORE_TABLES:
        return False
    return True

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        include_object=include_object
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
