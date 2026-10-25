"""Alembic environment: the async engine on ``DATABASE_URL``, JSON logs.

Logging is configured from ``logging.json`` unless the caller says otherwise
(``configure_logging = False`` in the config attributes, as the tests do).
"""

import asyncio
from pathlib import Path

from alembic import context
from sqlalchemy.engine import Connection

from app.database import database_url, make_engine
from app.models import Base
from primer_report import configure_logging

LOGGING_JSON = Path(__file__).resolve().parent.parent / "logging.json"

config = context.config
if config.attributes.get("configure_logging", True):
    configure_logging(LOGGING_JSON)

target_metadata = Base.metadata


def _migrate(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run() -> None:
    engine = make_engine(database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_migrate)
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline migrations are not supported: run against a database")
asyncio.run(_run())
