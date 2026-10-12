"""Database engines and sessions.

There are deliberately TWO engines pointing at two different Postgres servers:

* core  — tickets, reports, jurisdictions. Reporters appear only as opaque IDs.
* vault — identity data (encrypted phone, identity hashes, reporter-ID links).

Nothing in the core code path should import `vault_session`; only the citizen auth
service (Phase 1) does. Keeping them as separate servers (not just schemas) means a
leaked core DB dump or core DB credentials cannot reveal who reported what.

We use synchronous SQLAlchemy (psycopg 3). FastAPI runs sync dependencies in a thread
pool, and sync code is simpler to reason about for data-heavy work.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def core_engine() -> Engine:
    return create_engine(get_settings().core_database_url, pool_pre_ping=True)


@lru_cache
def vault_engine() -> Engine:
    return create_engine(get_settings().vault_database_url, pool_pre_ping=True)


def core_session() -> Session:
    return sessionmaker(bind=core_engine(), expire_on_commit=False)()


def vault_session() -> Session:
    return sessionmaker(bind=vault_engine(), expire_on_commit=False)()


def get_core_db() -> Iterator[Session]:
    """FastAPI dependency: a core DB session per request."""
    with core_session() as session:
        yield session
