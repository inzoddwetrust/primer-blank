"""Verbs of the project: ``python -m app.cli <verb> <args>``.

Which verb runs where is declared in ``primer.yaml`` (``verbs``); the machine
runs them in their service with their arguments in their order, knowing
nothing of what they do (contract 3 rule 7, protocol 8.2).
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text

from app.database import database_url, make_engine
from primer_report import configure_logging

LOGGING_JSON = Path(__file__).resolve().parent.parent / "logging.json"

logger = logging.getLogger(__name__)


async def set_setting(key: str, value: str) -> None:
    """Write ``key`` = ``value`` into ``app_settings``, over the old value."""
    engine = make_engine(database_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO app_settings (key, value) VALUES (:key, :value) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
                ),
                {"key": key, "value": value},
            )
    finally:
        await engine.dispose()
    logger.info("set-setting: %s", key, extra={"event": "cli.set_setting"})


def main(argv: Sequence[str]) -> int:
    """Run one verb; an unknown verb or a missing argument is refused first."""
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    verbs = parser.add_subparsers(dest="verb", required=True)
    setting = verbs.add_parser("set-setting")
    setting.add_argument("key")
    setting.add_argument("value")
    args = parser.parse_args(argv)
    configure_logging(LOGGING_JSON)
    asyncio.run(set_setting(args.key, args.value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
