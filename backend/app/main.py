"""The ASGI application: ``uvicorn --factory app.main:create_app``."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI

from app.config import Settings
from app.database import database_url, make_engine, measure, script_head
from app.editions import EDITIONS
from primer_report import Limits, PrimerReport, Seams

SERVICE = "blank"

# The largest request body the backend accepts, reported in /health.limits
# for the machine to compare with routes.api.max_body of primer.yaml.
MAX_UPLOAD_MB = 1

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, url: str | None = None) -> FastAPI:
    """Build the app; settings and database URL default to the environment."""
    settings = settings or Settings()
    engine = make_engine(url or database_url())
    head = script_head()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "edition %s, migrations head %s",
            settings.edition,
            head,
            extra={"event": "app.started"},
        )
        yield
        await engine.dispose()

    app = FastAPI(title=SERVICE, lifespan=lifespan)
    report = PrimerReport(
        service=SERVICE,
        release=settings.release,
        commit=settings.commit,
        edition=settings.edition,
        modules=list(EDITIONS[settings.edition]),
        limits=Limits(max_upload_mb=MAX_UPLOAD_MB),
        seams=Seams(provides=[], requires_satisfied=True),
        collect=partial(measure, engine, head),
    )
    report.install(app)
    return app
