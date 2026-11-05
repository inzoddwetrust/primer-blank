"""Probes of DM-66: protocol 9.5 -- every check under a timeout, a fallen
database reported as ``db: error`` with the revision measured before."""

import asyncio
import time

from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import make_engine, read_revision, script_head
from primer_report import Health
from tests.conftest import PROTOCOL_CHECK_TIMEOUT_S, client_for, report_app
from tests.test_report import hang, ok


def test_probe_DM_66_health_is_200_and_degraded_when_a_check_hangs() -> None:
    """One check hangs: 200, it is ``error``, the others are measured, the
    answer comes within the timeout and a margin. Pair: all ok -- ``ok``."""
    for client in client_for(report_app(checks={"db": ok, "redis": ok})):
        body = client.get("/health").json()
        assert body["checks"] == {"db": "ok", "redis": "ok"}
        assert body["status"] == "ok"

    for client in client_for(report_app(checks={"db": ok, "redis": hang, "queue": ok})):
        started = time.monotonic()
        response = client.get("/health")
        elapsed = time.monotonic() - started
        assert response.status_code == 200
        body = response.json()
        assert body["checks"] == {"db": "ok", "redis": "error", "queue": "ok"}
        assert body["status"] == "degraded"
        assert elapsed < PROTOCOL_CHECK_TIMEOUT_S + 1.0
        Health.model_validate(body)


class _Database:
    """The engine the report reads, switched in the middle of a test."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def revision(self) -> str:
        return await read_revision(self.engine)


def test_probe_DM_66_db_down_gives_checks_db_error_not_null_head_of_a_migrated_stack(
    migrated_db: str, unreachable_url: str
) -> None:
    """Measured at the head, then the database falls: ``db: error``,
    ``degraded``, and ``alembic_head`` is still the revision measured."""
    live, down = make_engine(migrated_db), make_engine(unreachable_url)
    database = _Database(live)
    head = script_head()
    try:
        for client in client_for(report_app(database.revision, head=head)):
            first = client.get("/health").json()
            assert first["checks"] == {"db": "ok", "schema": "ok"}
            assert first["alembic_head"] == head

            database.engine = down
            for _ in range(2):  # twin REPEAT: a second miss keeps it too
                response = client.get("/health")
                assert response.status_code == 200
                body = response.json()
                assert body["checks"] == {"db": "error", "schema": "error"}
                assert body["status"] == "degraded"
                assert body["alembic_head"] == head
                Health.model_validate(body)
    finally:
        asyncio.run(live.dispose())
        asyncio.run(down.dispose())
