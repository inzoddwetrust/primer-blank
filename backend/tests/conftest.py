"""Fixtures: the test database in a known state, settings, the app.

The suite runs only against a database whose name ends with ``_test``: on a
box the machine runs it in a throwaway container against an isolated database
(contract 3 rule 20), never against the live one, and the name is the last
guard against a wrong ``DATABASE_URL``.
"""

import asyncio
import os
import socket
from collections.abc import Awaitable, Callable, Iterator, Mapping
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import JsonValue
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.database import ALEMBIC_INI, at_head, make_engine
from app.main import create_app
from primer_report import Limits, PrimerReport, Seams

BACKEND = Path(__file__).resolve().parent.parent

RELEASE = "v0.0.0-test"
COMMIT = "0123456789abcdef0123456789abcdef01234567"

# Nothing listens on port 1 of the loopback: a connect is refused at once.
UNREACHABLE_PORT = 1

# Protocol 9.5: how long one check may take, written out here and not
# imported, so a longer timeout in the code fails the bounds of the tests.
PROTOCOL_CHECK_TIMEOUT_S = 2.0


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


@pytest.fixture
def silent_url(test_url: str) -> Iterator[str]:
    """A database that takes the connection and never says a word.

    The socket listens and is never read: the kernel completes the handshake
    from its backlog, the client sends its startup message and waits for the
    server's greeting, which never comes -- the same on every host.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(8)
        port: int = sock.getsockname()[1]
        yield (
            make_url(test_url)
            .set(host="127.0.0.1", port=port)
            .render_as_string(hide_password=False)
        )


def execute(url: str, *statements: str) -> None:
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
    execute(test_url, "DROP SCHEMA public CASCADE", "CREATE SCHEMA public")
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


# The service's seams as the machine renders them (DM-59); invented values.
SERVICE_SEAMS = {
    "SERVICE_API_URL": "http://primer-blank-service-app:8000",
    "SERVICE_TOKEN": "invented-service-token-000000000000001",
    "SERVICE_KEY": "sk_invented-service-key-0000000000001",
}


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate(
        {
            "EDITION": "core",
            "PRIMER_RELEASE": RELEASE,
            "PRIMER_COMMIT": COMMIT,
            **SERVICE_SEAMS,
        }
    )


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
def client_off_head(migrated_db: str, settings: Settings) -> Iterator[TestClient]:
    """Marked by alembic, at a revision that is not the head."""
    execute(migrated_db, "UPDATE alembic_version SET version_num = '0000'")
    yield from client_for(create_app(settings, migrated_db))


def report_app(
    db: Callable[[], Awaitable[str]] | None = None,
    *,
    head: str | None = None,
    checks: Mapping[str, Callable[[], Awaitable[bool]]] | None = None,
    details: Callable[[], Mapping[str, JsonValue]] | None = None,
) -> FastAPI:
    """An app with a ``PrimerReport`` of the given checks and nothing else."""
    app = FastAPI()
    PrimerReport(
        service="blank",
        release=RELEASE,
        commit=COMMIT,
        edition="core",
        modules=[],
        limits=Limits(max_upload_mb=1),
        seams=Seams(provides=[], requires_satisfied=True),
        db=db,
        head_checks={"schema": at_head(head)} if head is not None else None,
        checks=checks,
        details=details,
    ).install(app)
    return app


@pytest.fixture
def client_db_down(unreachable_url: str, settings: Settings) -> Iterator[TestClient]:
    yield from client_for(create_app(settings, unreachable_url))
