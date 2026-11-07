"""JSON log lines of TZ section 11 and the request id they carry.

Every line is one JSON object with ``LOG_FIELDS`` and, when the log call
gives one, ``LOG_CTX`` last (protocol 9.4). ``event`` is the ``event`` given
to the log call (``extra={"event": ...}``), else the logger name; ``msg`` is
the message with the traceback, if any, inside it, so a line is always one
line. ``request_id`` is the id of the request being served, or ``null``
outside a request.

``ctx`` is the stack's free object of the line (``extra={"ctx": {...}}``): a
job id, an error class -- never a person's data. A ``ctx`` that is not a JSON
object is left out and the line is written without it; one of any size is
written whole: over 8 KB the deploy machine cuts it, not the stack.

The formatter is named in a dictConfig file by ``"()"``, with ``service`` as
its argument; the release comes from ``PRIMER_RELEASE``, which the image
carries (contract 3 rule 19). Without it the formatter refuses to start.
"""

import json
import logging
import logging.config
import os
import re
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOG_FIELDS = ("ts", "level", "service", "release", "request_id", "event", "msg")
LOG_CTX = "ctx"

REQUEST_ID: ContextVar[str | None] = ContextVar("primer_request_id", default=None)

REQUEST_ID_HEADER = "x-request-id"

# An incoming id is kept only in this form: it lands in every log line of the
# request, so anything that could break or forge a line is replaced.
_REQUEST_ID_FORM = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class JsonFormatter(logging.Formatter):
    """One JSON object per record: ``LOG_FIELDS``, then ``LOG_CTX`` if given."""

    def __init__(self, service: str) -> None:
        super().__init__()
        if not service:
            raise ValueError("JsonFormatter needs the service name")
        release = os.environ.get("PRIMER_RELEASE", "")
        if not release:
            raise RuntimeError(
                "PRIMER_RELEASE is not set: every log line names the release"
            )
        self._service = service
        self._release = release

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            msg = f"{msg}\n{self.formatStack(record.stack_info)}"
        event = record.__dict__.get("event")
        line: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": self._service,
            "release": self._release,
            "request_id": REQUEST_ID.get(),
            "event": event if isinstance(event, str) and event else record.name,
            "msg": msg,
        }
        ctx = record.__dict__.get(LOG_CTX)
        if _json_object(ctx):
            line[LOG_CTX] = ctx
        return json.dumps(line, ensure_ascii=False)


def _json_object(value: object) -> bool:
    """``value`` is a dict that serializes to JSON as it is."""
    if not isinstance(value, dict):
        return False
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError, RecursionError):
        return False
    return True


def configure_logging(config_file: Path) -> None:
    """Apply the dictConfig JSON file the server is started with."""
    logging.config.dictConfig(json.loads(config_file.read_text(encoding="utf-8")))


FAILED_EVENT = "request.failed"

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    """Bind the request id for the request and echo it in the response.

    A well-formed ``X-Request-ID`` is kept; an absent, empty or malformed one
    is replaced by a fresh uuid. Of several ``X-Request-ID`` headers the last
    one is taken -- the one the nearest proxy wrote -- and judged alone: a
    malformed last one is replaced, never an earlier one used instead.

    It wraps the whole application, outside the framework's error middleware
    (``PrimerReport.install`` returns it for the factory to return), so the
    ``500`` that middleware sends carries the id too. An exception the
    application lets out is written here, inside the request, as one
    ``FAILED_EVENT`` line at level error with its traceback, and goes no
    further: by then the error middleware has sent the response, and the
    server's own line for it would come after the request, with no id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = ""
        for name, value in scope["headers"]:
            if name == REQUEST_ID_HEADER.encode():
                incoming = value.decode("latin-1")
        request_id = (
            incoming if _REQUEST_ID_FORM.fullmatch(incoming) else uuid.uuid4().hex
        )

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        token = REQUEST_ID.set(request_id)
        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            logger.exception(
                "%s %s failed",
                scope.get("method", ""),
                scope.get("path", ""),
                extra={"event": FAILED_EVENT},
            )
        finally:
            REQUEST_ID.reset(token)
