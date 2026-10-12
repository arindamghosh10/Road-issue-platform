"""Alembic environment for the CORE database (PostGIS)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.models.core import CoreBase

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = CoreBase.metadata

# Tables that belong to Postgres extensions (PostGIS's spatial_ref_sys, and on some
# servers postgis_topology / postgis_tiger_geocoder, whose schemas sit on the search
# path). Found by asking the database, so autogenerate never tries to drop them.
EXTENSION_TABLES_SQL = text("""
    SELECT DISTINCT c.relname FROM pg_class c
    JOIN pg_depend d ON d.objid = c.oid AND d.classid = 'pg_class'::regclass AND d.deptype = 'e'
    WHERE c.relkind IN ('r', 'p', 'v', 'm')
""")
extension_tables: set[str] = {"spatial_ref_sys"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name not in extension_tables
    if type_ == "index" and reflected and compare_to is None:
        return getattr(getattr(obj, "table", None), "name", None) not in extension_tables
    return True


def run_migrations_online() -> None:
    engine = create_engine(get_settings().core_database_url)
    with engine.connect() as connection:
        extension_tables.update(connection.execute(EXTENSION_TABLES_SQL).scalars())
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
