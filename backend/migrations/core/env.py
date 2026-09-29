"""Alembic environment for the CORE database (PostGIS)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models.core import CoreBase

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = CoreBase.metadata

# Tables owned by PostGIS itself; keep autogenerate from trying to drop them.
POSTGIS_TABLES = {"spatial_ref_sys", "topology", "layer"}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in POSTGIS_TABLES)


def run_migrations_online() -> None:
    engine = create_engine(get_settings().core_database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
