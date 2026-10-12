"""Alembic environment for the IDENTITY VAULT database."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models.vault import VaultBase

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = VaultBase.metadata


def run_migrations_online() -> None:
    engine = create_engine(get_settings().vault_database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
