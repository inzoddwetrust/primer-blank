"""Fixtures: the test database in a known state, settings, the app.

The suite runs only against a database whose name ends with ``_test``: on a
box the machine runs it in a throwaway container against an isolated database
(contract 3 rule 20), never against the live one, and the name is the last
guard against a wrong ``DATABASE_URL``.
"""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.database import ALEMBIC_INI, make_engine
from app.main import create_app

BACKEND = Path(__file__).resolve().parent.parent

RELEASE = "v0.0.0-test"
COMMIT = "0123456789abcdef0123456789abcdef01234567"

# Nothing listens on port 1 of the loopback: a connect is refused at once.
UNREACHABLE_PORT = 1


@pytest.fixture(scope="session")
def test_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.exit("DATABASE_URL is not set", returncode=2)
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.exit(
            f"refusing to run against database {name!r}: its name must end with _test",
            returncode=2,
        )
    return url


@pytest.fixture
def unreachable_url(test_url: str) -> str:
    return (
        make_url(test_url)
        .set(host="127.0.0.1", port=UNREACHABLE_PORT)
        .render_as_string(hide_password=False)
    )


def _execute(url: str, *statements: str) -> None:
    async def run() -> None:
        engine = make_engine(url)
        try:
            async with engine.begin() as conn:
                for statement in statements:
                    await conn.execute(text(statement))
        finally:
            await engine.dispose()

    asyncio.run(run())


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logging"] = False
    return config


@pytest.fixture
def clean_db(test_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """An empty public schema: no tables, no alembic_version."""
    monkeypatch.setenv("DATABASE_URL", test_url)
    _execute(test_url, "DROP SCHEMA public CASCADE", "CREATE SCHEMA public")
    return test_url


@pytest.fixture
def migrated_db(clean_db: str) -> str:
    """The schema at the head of the migrations."""
    command.upgrade(alembic_config(), "head")
    return clean_db


def query_scalar(url: str, statement: str) -> object:
    async def run() -> object:
        engine = make_engine(url)
        try:
            async with engine.connect() as conn:
                return await conn.scalar(text(statement))
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture
def settings() -> Settings:
    return Settings(EDITION="core", PRIMER_RELEASE=RELEASE, PRIMER_COMMIT=COMMIT)


def client_for(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_at_head(migrated_db: str, settings: Settings) -> Iterator[TestClient]:
    yield from client_for(create_app(settings, migrated_db))


@pytest.fixture
def client_not_migrated(clean_db: str, settings: Settings) -> Iterator[TestClient]:
    yield from client_for(create_app(settings, clean_db))


@pytest.fixture
def client_db_down(unreachable_url: str, settings: Settings) -> Iterator[TestClient]:
    yield from client_for(create_app(settings, unreachable_url))
