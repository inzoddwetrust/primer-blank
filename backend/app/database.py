"""The database: its URL, the engine, and what ``/health`` measures in it."""

import os
from collections.abc import Callable
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from primer_report import CHECK_TIMEOUT_S

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

# A connect attempt gives up no later than a health check does.
CONNECT_TIMEOUT_S = CHECK_TIMEOUT_S


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


async def read_revision(engine: AsyncEngine) -> str:
    """The database's revision, in one query -- the ``db`` check of ``/health``.

    No ``alembic_version`` (a clean database) and an empty one both raise:
    a revision that cannot be read is ``db: error`` (protocol 9.5).
    """
    async with engine.connect() as conn:
        revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    if not isinstance(revision, str) or not revision:
        raise LookupError("alembic_version holds no revision")
    return revision


def at_head(head: str) -> Callable[[str], bool]:
    """The ``schema`` check: the revision read is ``head``."""

    def judge(revision: str) -> bool:
        return revision == head

    return judge
