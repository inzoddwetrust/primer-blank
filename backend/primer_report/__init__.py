"""primer-report: what a Primer stack shows the deploy machine (TZ section 11).

Three lines in the application's ``main.py``::

    from primer_report import PrimerReport
    report = PrimerReport(service=..., release=..., ..., collect=...)
    report.install(app)

``install`` mounts ``GET /health`` and ``GET /ready`` and the request-id
middleware. JSON logs come from ``JsonFormatter``, named in the dictConfig file
the server is started with (``uvicorn --log-config``).
"""

from primer_report.health import (
    Health,
    Limits,
    PrimerReport,
    Ready,
    Seams,
    Snapshot,
)
from primer_report.logs import (
    LOG_FIELDS,
    REQUEST_ID,
    JsonFormatter,
    RequestIdMiddleware,
    configure_logging,
)

__all__ = [
    "LOG_FIELDS",
    "REQUEST_ID",
    "Health",
    "JsonFormatter",
    "Limits",
    "PrimerReport",
    "Ready",
    "RequestIdMiddleware",
    "Seams",
    "Snapshot",
    "configure_logging",
]
