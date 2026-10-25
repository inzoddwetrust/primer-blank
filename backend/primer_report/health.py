"""``GET /health`` and ``GET /ready`` in the form of TZ section 11.

``/health`` always answers 200 with the full document: the machine reads it
both from a healthy and from a degraded stack. ``status`` is ``ok`` only when
every check is. ``/ready`` answers 200 exactly when every check is ok, else
503 naming the failing checks.

The stack's state is measured on every request by ``collect``; nothing is
cached, so an answer is never older than the request.
"""

import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from primer_report.logs import RequestIdMiddleware

CheckState = Literal["ok", "error"]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Seams(_Closed):
    """What the stack provides to others and whether its requires are met."""

    provides: list[str]
    requires_satisfied: bool


class Limits(_Closed):
    """Limits of the live application the machine compares host knobs with."""

    max_upload_mb: int = Field(ge=0)


class Health(_Closed):
    """The ``/health`` document of TZ section 11."""

    service: str = Field(min_length=1)
    release: str = Field(min_length=1)
    commit: str = Field(min_length=1)
    alembic_head: str | None
    uptime_s: int = Field(ge=0, strict=True)
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckState] = Field(min_length=1)
    seams: Seams
    limits: Limits
    edition: str = Field(min_length=1)
    modules: list[str]


class Ready(_Closed):
    """The ``/ready`` document: ready, or the names of the failing checks."""

    status: Literal["ready", "not_ready"]
    failing: list[str]


@dataclass(frozen=True)
class Snapshot:
    """One measurement of the stack: each check passed or not, the db revision."""

    checks: Mapping[str, bool]
    alembic_head: str | None


class PrimerReport:
    """The health router of one stack; ``install`` puts it on the app."""

    def __init__(
        self,
        *,
        service: str,
        release: str,
        commit: str,
        edition: str,
        modules: list[str],
        limits: Limits,
        seams: Seams,
        collect: Callable[[], Awaitable[Snapshot]],
    ) -> None:
        self._fixed = {
            "service": service,
            "release": release,
            "commit": commit,
            "edition": edition,
            "modules": list(modules),
            "limits": limits,
            "seams": seams,
        }
        self._collect = collect
        self._started = time.monotonic()
        self.router = APIRouter()
        self.router.add_api_route("/health", self.health, methods=["GET"])
        self.router.add_api_route(
            "/ready",
            self.ready,
            methods=["GET"],
            responses={503: {"model": Ready}},
        )

    def install(self, app: FastAPI) -> None:
        """Mount ``/health``, ``/ready`` and the request-id middleware."""
        app.include_router(self.router)
        app.add_middleware(RequestIdMiddleware)

    async def health(self) -> Health:
        """The full document; 200 whatever the state."""
        snapshot = await self._collect()
        checks: dict[str, CheckState] = {
            name: "ok" if passed else "error"
            for name, passed in snapshot.checks.items()
        }
        return Health.model_validate(
            {
                **self._fixed,
                "alembic_head": snapshot.alembic_head,
                "uptime_s": int(time.monotonic() - self._started),
                "status": "ok" if all(snapshot.checks.values()) else "degraded",
                "checks": checks,
            }
        )

    async def ready(self) -> JSONResponse:
        """200 when every check passes, else 503 with the failing names."""
        snapshot = await self._collect()
        failing = sorted(name for name, ok in snapshot.checks.items() if not ok)
        body = Ready(status="not_ready" if failing else "ready", failing=failing)
        return JSONResponse(body.model_dump(), status_code=503 if failing else 200)
