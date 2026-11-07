"""primer-report: what a Primer stack shows the deploy machine (protocol 9).

Three lines in the application's ``main.py``::

    from primer_report import PrimerReport
    report = PrimerReport(service=..., release=..., ..., db=..., details=...)
    return report.install(app)

``install`` mounts ``GET /health`` and ``GET /ready`` and returns the app
inside the request-id middleware: the factory (``uvicorn --factory``) returns
that, so the middleware is outside the framework's own and a ``500`` carries
the id too. JSON logs come from ``JsonFormatter``, named in the dictConfig file
the server is started with (``uvicorn --log-config``).
"""

from primer_report.health import (
    CHECK_TIMEOUT_S,
    DB,
    DETAILS_LIMIT,
    Health,
    Limits,
    PrimerReport,
    Ready,
    Seams,
    free_size,
)
from primer_report.logs import (
    FAILED_EVENT,
    LOG_CTX,
    LOG_FIELDS,
    REQUEST_ID,
    JsonFormatter,
    RequestIdMiddleware,
    configure_logging,
)

__all__ = [
    "CHECK_TIMEOUT_S",
    "DB",
    "DETAILS_LIMIT",
    "FAILED_EVENT",
    "LOG_CTX",
    "LOG_FIELDS",
    "REQUEST_ID",
    "Health",
    "JsonFormatter",
    "Limits",
    "PrimerReport",
    "Ready",
    "RequestIdMiddleware",
    "Seams",
    "configure_logging",
    "free_size",
]
