"""``GET /health`` and ``GET /ready`` of protocol 9.1, 9.2 and 9.5.

``/health`` always answers 200 with the full document: the machine reads it
both from a healthy and from a degraded stack. ``status`` is ``ok`` only when
every check is. ``/ready`` answers 200 exactly when every check is ok, else
503 naming the failing checks.

Every request measures the stack anew. Each check runs under
``CHECK_TIMEOUT_S``, all of them at once; one that raises or does not answer
in time is ``error``, and the others are still measured (protocol 9.5). The
database is one check, ``db``: one read of its revision, which is also
``alembic_head``. Checks of the revision (``head_checks``) are computed from
that read, with no query of their own; with no revision read they are
``error``.

The one thing kept between requests is the last revision read: a database
that falls after it was measured reports ``db: error`` with that revision as
``alembic_head`` (protocol 9.1); before the first read it is ``null``.

``details`` is the stack's free object, built from the process's memory on
every ``/health``; one that is not a JSON object or is over
``DETAILS_LIMIT`` bytes is left out of the answer and named in the log.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from primer_report.logs import RequestIdMiddleware

CheckState = Literal["ok", "error"]

DB = "db"
"""The name of the database check in ``checks``."""

CHECK_TIMEOUT_S = 2.0
"""How long one check may take before it is ``error`` (protocol 9.5: 1--2 s)."""

DETAILS_LIMIT = 8192
"""The most ``details`` may take: bytes of its compact JSON in UTF-8 -- the
measure the deploy machine checks it with (protocol 9.1)."""

logger = logging.getLogger(__name__)

_DETAILS = TypeAdapter(dict[str, JsonValue])


def free_size(value: JsonValue) -> int:
    """The bytes of ``value`` as compact JSON in UTF-8."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8"))


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
    """The ``/health`` document of protocol 9.1.

    ``details`` is optional: an answer without it leaves the key out (the
    model's default is not sent, ``null`` is refused).
    """

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
    details: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def _bounded(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        size = free_size(value)
        if size > DETAILS_LIMIT:
            raise ValueError(f"details takes {size} bytes, over {DETAILS_LIMIT}")
        return value


class Ready(_Closed):
    """The ``/ready`` document: ready, or the names of the failing checks."""

    status: Literal["ready", "not_ready"]
    failing: list[str]


async def _within[T](call: Callable[[], Awaitable[T]]) -> T | Exception:
    """The result of ``call``, or what stopped it -- a timeout is one."""
    try:
        return await asyncio.wait_for(call(), CHECK_TIMEOUT_S)
    except Exception as error:  # every failure of a check is its `error`
        return error


async def _no_db() -> str | None:
    return None


def _refuse(ctx: dict[str, JsonValue]) -> None:
    logger.warning(
        "details left out of /health",
        extra={"event": "health.details_refused", "ctx": ctx},
    )


class PrimerReport:
    """The health router of one stack; ``install`` puts it on the app.

    ``db`` reads the database's revision in one query and raises when there
    is none to read (no ``alembic_version``, an empty one); ``None`` is a
    stack without migrations, whose ``alembic_head`` is always ``null``.
    ``head_checks`` judge the revision read; ``checks`` are the stack's other
    checks (Redis and the like). A check is a coroutine that can be cancelled:
    one that blocks the event loop or swallows the cancellation is not held
    by the timeout. ``details`` builds the free object of ``/health`` from
    memory -- no database, no network.

    A check that turns to ``error`` is logged once, by the class of what
    stopped it (``health.check_failed``); it is logged again only after it was
    ``ok`` in between.
    """

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
        db: Callable[[], Awaitable[str]] | None = None,
        head_checks: Mapping[str, Callable[[str], bool]] | None = None,
        checks: Mapping[str, Callable[[], Awaitable[bool]]] | None = None,
        details: Callable[[], Mapping[str, JsonValue]] | None = None,
    ) -> None:
        head_checks = dict(head_checks or {})
        checks = dict(checks or {})
        if head_checks and db is None:
            raise ValueError("head_checks judge the revision: they need db")
        names = [*([DB] if db is not None else []), *head_checks, *checks]
        if not names:
            raise ValueError("a stack reports at least one check (protocol 9.1)")
        if len(set(names)) != len(names):
            raise ValueError(f"check names repeat: {names}")
        self._fixed = {
            "service": service,
            "release": release,
            "commit": commit,
            "edition": edition,
            "modules": list(modules),
            "limits": limits,
            "seams": seams,
        }
        # A wrong fixed field fails the start, not every request.
        Health.model_validate(
            {
                **self._fixed,
                "alembic_head": None,
                "uptime_s": 0,
                "status": "ok",
                "checks": dict.fromkeys(names, "ok"),
            }
        )
        self._db = db
        self._head_checks = head_checks
        self._checks = checks
        self._details = details
        self._last_head: str | None = None
        self._failed: set[str] = set()
        self._started = time.monotonic()
        self.router = APIRouter()
        self.router.add_api_route(
            "/health",
            self.health,
            methods=["GET"],
            response_model_exclude_unset=True,
        )
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

    async def _measure(self) -> dict[str, CheckState]:
        """Every check once, at the same time; the revision read is kept."""
        read: Callable[[], Awaitable[str | None]] = self._db or _no_db
        revision, *outcomes = await asyncio.gather(
            _within(read), *(_within(check) for check in self._checks.values())
        )
        results: dict[str, bool | Exception | None] = {}
        if self._db is not None:
            if isinstance(revision, str) and revision:
                self._last_head = revision
                results[DB] = True
                for name, judge in self._head_checks.items():
                    try:
                        results[name] = judge(revision) is True
                    except Exception as error:  # a judge that raises is `error`
                        results[name] = error
            else:
                results[DB] = revision if isinstance(revision, Exception) else None
                results.update(dict.fromkeys(self._head_checks))
        for name, outcome in zip(self._checks, outcomes, strict=True):
            if isinstance(outcome, Exception):
                results[name] = outcome
            else:
                results[name] = outcome is True or None
        return {name: self._state(name, outcome) for name, outcome in results.items()}

    def _state(self, name: str, outcome: bool | Exception | None) -> CheckState:
        """``ok`` for ``True``; anything else is ``error``, logged on the turn."""
        if outcome is True:
            self._failed.discard(name)
            return "ok"
        if name not in self._failed:
            self._failed.add(name)
            logger.warning(
                "check %s is error",
                name,
                extra={
                    "event": "health.check_failed",
                    "ctx": {
                        "check": name,
                        "error": (
                            type(outcome).__name__
                            if isinstance(outcome, Exception)
                            else None
                        ),
                    },
                },
            )
        return "error"

    def _free(self) -> dict[str, JsonValue] | None:
        """``details`` for this answer, or ``None`` when there is none to send."""
        if self._details is None:
            return None
        try:
            built = self._details()
        except Exception as error:  # a failing builder leaves details out
            _refuse({"reason": "error", "error": type(error).__name__})
            return None
        try:
            value = _DETAILS.validate_python(built, strict=True)
            size = free_size(value)
        except (ValidationError, TypeError, ValueError, RecursionError):
            _refuse({"reason": "type"})
            return None
        if size > DETAILS_LIMIT:
            _refuse({"reason": "size", "size": size})
            return None
        return value

    async def health(self) -> Health:
        """The full document; 200 whatever the state."""
        checks = await self._measure()
        document: dict[str, object] = {
            **self._fixed,
            "alembic_head": self._last_head if self._db is not None else None,
            "uptime_s": int(time.monotonic() - self._started),
            "status": "ok" if all(s == "ok" for s in checks.values()) else "degraded",
            "checks": checks,
        }
        details = self._free()
        if details is not None:
            document["details"] = details
        return Health.model_validate(document)

    async def ready(self) -> JSONResponse:
        """200 when every check passes, else 503 with the failing names."""
        checks = await self._measure()
        failing = sorted(name for name, state in checks.items() if state != "ok")
        body = Ready(status="not_ready" if failing else "ready", failing=failing)
        return JSONResponse(body.model_dump(), status_code=503 if failing else 200)
