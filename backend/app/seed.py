"""Seed profiles: ``python -m app.seed <profile>``.

Which profile runs when is declared in ``primer.yaml`` (``seeds``); the
machine knows no profile names (contract 3 rule 17). Every profile is
idempotent: run again, it changes nothing.
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import database_url, make_engine
from primer_report import configure_logging

LOGGING_JSON = Path(__file__).resolve().parent.parent / "logging.json"

logger = logging.getLogger(__name__)


async def bootstrap(engine: AsyncEngine) -> None:
    """Record when the instance was installed; an existing record is kept."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "INSERT INTO app_settings (key, value) VALUES ('installed_at', :at) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"at": datetime.now(UTC).isoformat()},
        )
    logger.info(
        "bootstrap: %d row(s) written",
        result.rowcount,
        extra={"event": "seed.bootstrap"},
    )


PROFILES: dict[str, Callable[[AsyncEngine], Coroutine[None, None, None]]] = {
    "bootstrap": bootstrap,
}


async def _run(profile: str) -> None:
    engine = make_engine(database_url())
    try:
        await PROFILES[profile](engine)
    finally:
        await engine.dispose()


def main(argv: Sequence[str]) -> int:
    """Run one profile; an unknown name is refused before anything runs."""
    parser = argparse.ArgumentParser(prog="python -m app.seed")
    parser.add_argument("profile", choices=sorted(PROFILES))
    args = parser.parse_args(argv)
    configure_logging(LOGGING_JSON)
    asyncio.run(_run(args.profile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
