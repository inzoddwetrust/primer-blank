"""The ASGI application: ``uvicorn --factory app.main:create_app``."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI, Response

from app.config import Settings
from app.database import at_head, database_url, make_engine, read_revision, script_head
from app.editions import EDITIONS
from primer_report import Limits, PrimerReport, Seams

SERVICE = "blank"

# The largest request body the backend accepts, reported in /health.limits
# for the machine to compare with routes.api.max_body of primer.yaml.
MAX_UPLOAD_MB = 1

# What the product gives its service (primer.yaml provides): the webhook
# route below. The machine renders its URL from domains.api; the backend
# says it serves it.
PROVIDES = ["PRODUCT_WEBHOOK_URL"]
WEBHOOK = "/internal/service/webhook"


def requires_satisfied(settings: Settings) -> bool:
    """Every seam of the service came: its address, its token, its key."""
    return all((settings.service_api_url, settings.service_token, settings.service_key))


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
            extra={
                "event": "app.started",
                "ctx": {"edition": settings.edition, "script_head": head},
            },
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
        seams=Seams(
            provides=list(PROVIDES), requires_satisfied=requires_satisfied(settings)
        ),
        db=partial(read_revision, engine),
        head_checks={"schema": at_head(head)},
        details=lambda: {"script_head": head},
    )
    report.install(app)

    @app.post(WEBHOOK, status_code=204)
    async def webhook() -> Response:
        """The service's calls land here; the blank takes them and does
        nothing more."""
        return Response(status_code=204)

    return app
