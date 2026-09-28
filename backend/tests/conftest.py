"""Test setup.

Unit tests need nothing. Database tests (marked `db`) run only when separate TEST
databases are configured, so they can never wipe a real/dev database:

    TEST_CORE_DATABASE_URL=postgresql+psycopg://.../roadwatch_core_test
    TEST_VAULT_DATABASE_URL=postgresql+psycopg://.../roadwatch_vault_test
"""

import os

import pytest

# Must happen before anything reads settings.
os.environ["APP_ENV"] = "test"
os.environ["STORAGE_BACKEND"] = "memory"
os.environ["TASKS_EAGER"] = "true"
os.environ["VISION_PROVIDER"] = "stub"
os.environ["OTP_PROVIDER"] = "stub"
os.environ["EMAIL_BACKEND"] = "log"
TEST_CORE = os.environ.get("TEST_CORE_DATABASE_URL")
TEST_VAULT = os.environ.get("TEST_VAULT_DATABASE_URL")
if TEST_CORE and TEST_VAULT:
    os.environ["CORE_DATABASE_URL"] = TEST_CORE
    os.environ["VAULT_DATABASE_URL"] = TEST_VAULT


def pytest_configure(config):
    config.addinivalue_line("markers", "db: needs TEST_CORE/VAULT_DATABASE_URL")


def pytest_collection_modifyitems(config, items):
    if TEST_CORE and TEST_VAULT:
        return
    skip = pytest.mark.skip(reason="set TEST_CORE_DATABASE_URL and TEST_VAULT_DATABASE_URL")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_db():
    """Migrate both test databases and load the sample seed once per test session."""
    from alembic import command
    from alembic.config import Config

    ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    for name in ("core", "vault"):
        cfg = Config(ini, ini_section=name)
        cfg.set_main_option(
            "script_location",
            os.path.join(os.path.dirname(ini), "migrations", name),
        )
        command.upgrade(cfg, "head")

    from app.seed.run import run

    run(reset=True)


@pytest.fixture
def clean_db(migrated_db):
    """Empty the per-test tables (tickets, reports, citizens) but keep the seed data."""
    from sqlalchemy import text

    from app.db import core_engine, vault_engine
    from app.storage import get_store

    with core_engine().begin() as conn:
        conn.execute(text(
            "TRUNCATE notifications, fix_confirmations, fix_proofs, ticket_events, reports, "
            "tickets, reporters CASCADE"
        ))
        conn.execute(text("UPDATE officials SET totp_enabled = false, totp_secret = NULL"))
    with vault_engine().begin() as conn:
        conn.execute(text("TRUNCATE reporter_links, otp_challenges, identities CASCADE"))
    get_store().objects.clear()
    yield


@pytest.fixture
def client(clean_db):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
