"""The database: its URL, the engine, and what ``/health`` measures in it."""

import asyncio
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from primer_report import Snapshot

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

# A health request must answer even when the database does not: the connect
# attempt gives up after CONNECT_TIMEOUT_S, the whole measurement after
# MEASURE_TIMEOUT_S.
CONNECT_TIMEOUT_S = 2
MEASURE_TIMEOUT_S = 3


def database_url() -> str:
    """``DATABASE_URL`` of the environment; absent or empty stops with its name."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def make_engine(url: str) -> AsyncEngine:
    """An engine that opens a connection per use and fails fast on connect."""
    return create_async_engine(
        url, poolclass=NullPool, connect_args={"timeout": CONNECT_TIMEOUT_S}
    )


def script_head() -> str:
    """The single head revision of the migrations shipped with this code."""
    config = Config(str(ALEMBIC_INI))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("the migrations have no head revision")
    return head


async def _revision(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        exists = await conn.scalar(text("SELECT to_regclass('alembic_version')"))
        if exists is None:
            return None
        revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        return revision if isinstance(revision, str) else None


async def measure(engine: AsyncEngine, head: str) -> Snapshot:
    """``db``: the database answers; ``schema``: it stands at ``head``."""
    try:
        revision = await asyncio.wait_for(_revision(engine), MEASURE_TIMEOUT_S)
    except (OSError, TimeoutError, SQLAlchemyError):
        return Snapshot(checks={"db": False, "schema": False}, alembic_head=None)
    return Snapshot(
        checks={"db": True, "schema": revision == head}, alembic_head=revision
    )
