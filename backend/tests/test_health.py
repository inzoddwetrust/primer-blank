"""``/health`` and ``/ready`` in every state of the database."""

import asyncio
import logging
import time

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event

from app.config import Settings
from app.database import make_engine, read_revision, script_head
from app.main import MAX_UPLOAD_MB, create_app
from primer_report import Health
from tests.conftest import (
    COMMIT,
    PROTOCOL_CHECK_TIMEOUT_S,
    RELEASE,
    SERVICE_SEAMS,
    alembic_config,
    client_for,
    execute,
    query_scalar,
    report_app,
)

# Protocol 9.1, written out here and not taken from the model: a field the
# model loses or gains must fail this list, not follow it.
FIELDS_11 = {
    "service",
    "release",
    "commit",
    "alembic_head",
    "uptime_s",
    "status",
    "checks",
    "seams",
    "limits",
    "edition",
    "modules",
}
DETAILS = "details"

# state -> (status, checks, alembic_head is the head)
EXPECTED = {
    "client_at_head": ("ok", {"db": "ok", "schema": "ok"}, True),
    "client_not_migrated": ("degraded", {"db": "error", "schema": "error"}, False),
    "client_db_down": ("degraded", {"db": "error", "schema": "error"}, False),
}


@pytest.mark.parametrize("state", sorted(EXPECTED))
def test_probe_DM_26_health_matches_schema_11(
    state: str, request: pytest.FixtureRequest
) -> None:
    """The eleven fields of protocol 9.1 and, given, ``details`` -- an object.

    Changed by DM-66 (protocol 9.1/9.4 v1.7: the optional ``details``, ``ctx``;
    9.5: a revision that is not read is ``db: error``): the blank's
    ``details`` is checked apart from the eleven fields, and a clean database
    is ``db: error``, no longer ``db: ok``.

    Changed by DM-59 (protocol 4, contract 3 rule 21; the gate's answer,
    item 3: ``/health.seams`` as it is): the blank provides
    ``PRODUCT_WEBHOOK_URL`` to its service and its requires are the service's
    three seams -- ``seams`` is no longer ``[]`` and ``True`` by constant.

    Changed by DM-70 (by the dispatcher's word, before the change): the stack
    is named by its repository; the blank is ``name: primer-blank`` (contract
    3 rule 32, DM-70).
    """
    client: TestClient = request.getfixturevalue(state)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) - {DETAILS} == FIELDS_11
    assert isinstance(body[DETAILS], dict)
    assert body[DETAILS] == {"script_head": script_head()}
    Health.model_validate(body)

    status, checks, at_head = EXPECTED[state]
    assert body["status"] == status
    assert body["checks"] == checks
    assert body["alembic_head"] == (script_head() if at_head else None)
    assert body["service"] == "primer-blank"
    assert body["release"] == RELEASE
    assert body["commit"] == COMMIT
    assert type(body["uptime_s"]) is int
    assert body["uptime_s"] >= 0
    assert body["seams"] == {
        "provides": ["PRODUCT_WEBHOOK_URL"],
        "requires_satisfied": True,
    }
    assert body["limits"] == {"max_upload_mb": MAX_UPLOAD_MB}
    assert body["edition"] == "core"
    assert body["modules"] == []


@pytest.mark.parametrize(
    ("state", "code", "failing"),
    [
        ("client_at_head", 200, []),
        ("client_not_migrated", 503, ["db", "schema"]),
        ("client_db_down", 503, ["db", "schema"]),
    ],
)
def test_ready_only_at_head(
    state: str, code: int, failing: list[str], request: pytest.FixtureRequest
) -> None:
    """Changed by DM-66 (protocol 9.1/9.4 v1.7: the optional ``details``,
    ``ctx``; 9.5: a revision that is not read is ``db: error``): a clean
    database fails ``db`` as well as ``schema``."""
    client: TestClient = request.getfixturevalue(state)
    response = client.get("/ready")
    assert response.status_code == code
    assert response.json() == {
        "status": "ready" if code == 200 else "not_ready",
        "failing": failing,
    }


def test_health_follows_the_database_without_restart(
    clean_db: str, settings: Settings
) -> None:
    """Measured per request: migrating a running app turns it ready."""
    for client in client_for(create_app(settings, clean_db)):
        assert client.get("/ready").status_code == 503
        command.upgrade(alembic_config(), "head")
        assert client.get("/ready").status_code == 200
        assert client.get("/health").json()["alembic_head"] == script_head()


def test_health_answers_in_bounded_time_when_the_database_is_silent(
    silent_url: str, settings: Settings
) -> None:
    """A database that takes the connection and never answers is given up on
    within the check's timeout.

    Changed by DM-66: the silent database is a local socket that never
    answers, not ``10.255.255.1``, whose behaviour the network decides (it may
    refuse at once); the bound is protocol 9.5's timeout and a margin.
    """
    for client in client_for(create_app(settings, silent_url)):
        started = time.monotonic()
        body = client.get("/health").json()
        elapsed = time.monotonic() - started
        assert body["checks"] == {"db": "error", "schema": "error"}
        assert body["status"] == "degraded"
        assert elapsed < PROTOCOL_CHECK_TIMEOUT_S + 1.5


def test_the_health_model_is_closed(client_at_head: TestClient) -> None:
    """The model the probe validates with refuses a field TZ 11 does not name."""
    body = client_at_head.get("/health").json()
    with pytest.raises(ValidationError, match="extra"):
        Health.model_validate({**body, "version": "x"})
    with pytest.raises(ValidationError, match="extra"):
        Health.model_validate({**body, "limits": {"max_upload_mb": 1, "x": 2}})


def test_a_database_off_the_head_reports_the_revision_it_stands_at(
    client_off_head: TestClient,
) -> None:
    """Read, but not the head: ``db`` ok, ``schema`` error, the real revision."""
    body = client_off_head.get("/health").json()
    assert body["checks"] == {"db": "ok", "schema": "error"}
    assert body["status"] == "degraded"
    assert body["alembic_head"] == "0000"
    assert client_off_head.get("/ready").json()["failing"] == ["schema"]


def test_an_empty_alembic_version_is_db_error(
    migrated_db: str, settings: Settings
) -> None:
    """Twin EMPTY: the table is there and holds no revision -- not read."""
    execute(migrated_db, "DELETE FROM alembic_version")
    for client in client_for(create_app(settings, migrated_db)):
        body = client.get("/health").json()
        assert body["checks"] == {"db": "error", "schema": "error"}
        assert body["alembic_head"] is None
        assert body["status"] == "degraded"


@pytest.mark.parametrize(
    "state",
    ["client_at_head", "client_off_head", "client_not_migrated", "client_db_down"],
)
def test_ready_fails_exactly_the_checks_health_reports_not_ok(
    state: str, request: pytest.FixtureRequest
) -> None:
    client: TestClient = request.getfixturevalue(state)
    checks = client.get("/health").json()["checks"]
    ready = client.get("/ready")
    failing = sorted(name for name, value in checks.items() if value != "ok")
    assert ready.json()["failing"] == failing
    assert ready.status_code == (503 if failing else 200)


def test_one_query_reads_db_and_alembic_head(migrated_db: str) -> None:
    """Protocol 9.5: the database check and the revision are one statement."""
    engine = make_engine(migrated_db)
    statements: list[str] = []

    def record(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    app = report_app(lambda: read_revision(engine), head=script_head())
    try:
        for client in client_for(app):
            client.get("/health")  # the first connect may also ask the server
            for path in ("/health", "/ready"):
                statements.clear()
                assert client.get(path).status_code == 200
                assert statements == ["SELECT version_num FROM alembic_version"]
    finally:
        asyncio.run(engine.dispose())
    assert query_scalar(migrated_db, "SELECT count(*) FROM alembic_version") == 1


def test_a_stack_without_migrations_reports_no_head() -> None:
    """Twin LACK: no ``db`` -- ``alembic_head`` is null and the stack is ok."""

    async def redis() -> bool:
        return True

    for client in client_for(report_app(checks={"redis": redis})):
        body = client.get("/health").json()
        assert body["checks"] == {"redis": "ok"}
        assert body["status"] == "ok"
        assert body["alembic_head"] is None
        assert "details" not in body


def test_health_never_waits_longer_than_a_check(
    silent_url: str, settings: Settings
) -> None:
    """A silent database leaves /ready as fast as /health."""
    for client in client_for(create_app(settings, silent_url)):
        started = time.monotonic()
        assert client.get("/ready").status_code == 503
        assert time.monotonic() - started < PROTOCOL_CHECK_TIMEOUT_S + 1.5


def test_read_revision_raises_on_an_empty_alembic_version(migrated_db: str) -> None:
    """Twin EMPTY of the reader: no row is no revision, not ``None``."""
    execute(migrated_db, "DELETE FROM alembic_version")
    engine = make_engine(migrated_db)
    try:
        with pytest.raises(LookupError, match="no revision"):
            asyncio.run(read_revision(engine))
    finally:
        asyncio.run(engine.dispose())


@pytest.mark.parametrize("missing", ["SERVICE_API_URL", "SERVICE_TOKEN", "SERVICE_KEY"])
def test_requires_satisfied_follows_every_seam_of_the_service(
    missing: str, test_url: str
) -> None:
    """DM-59, twin LACK: a seam of the service did not come -- the blank says
    so; the machine's ``seams_verify`` reads it (``requires-unsatisfied``)."""
    seams = {**SERVICE_SEAMS, missing: ""}
    given = Settings.model_validate(
        {"EDITION": "core", "PRIMER_RELEASE": RELEASE, "PRIMER_COMMIT": COMMIT, **seams}
    )
    for client in client_for(create_app(given, test_url)):
        body = client.get("/health").json()
        assert body["seams"] == {
            "provides": ["PRODUCT_WEBHOOK_URL"],
            "requires_satisfied": False,
        }


WEBHOOK = "/internal/service/webhook"
TOKEN = SERVICE_SEAMS["SERVICE_TOKEN"]


@pytest.mark.parametrize(
    ("authorization", "code"),
    [
        (f"Bearer {TOKEN}", 204),
        (f"bearer {TOKEN}", 204),  # the scheme in any case (RFC 7235)
        (None, 401),
        ("Bearer invented-other-token-0000000000001", 401),
        ("Bearer ", 401),
        (f"Token {TOKEN}", 401),
        (TOKEN, 401),
        (f"Bearer  {TOKEN}", 401),  # the token exactly: no space before it
        (f"Bearer {TOKEN}x", 401),
    ],
    ids=[
        "own",
        "own-lower",
        "none",
        "other",
        "empty",
        "scheme",
        "bare",
        "space",
        "longer",
    ],
)
def test_the_webhook_takes_only_its_service(
    authorization: str | None, code: int, client_at_head: TestClient
) -> None:
    """DM-70: ``PRODUCT_WEBHOOK_URL`` is on the public ``api`` domain, so the
    route answers its service alone -- ``Authorization: Bearer
    <SERVICE_TOKEN>``; any other caller gets 401. The pair: own -- 204."""
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client_at_head.post(WEBHOOK, json={"x": 1}, headers=headers)
    assert response.status_code == code
    if code == 401:
        assert response.headers["www-authenticate"] == "Bearer"
        assert TOKEN not in response.text


def test_a_second_authorization_does_not_override_the_first(
    client_at_head: TestClient,
) -> None:
    """Twin REPEAT: two headers, the first foreign -- the first decides."""
    headers = [("Authorization", "Bearer other"), ("Authorization", f"Bearer {TOKEN}")]
    response = client_at_head.post(WEBHOOK, headers=headers)
    assert response.status_code == 401
    assert client_at_head.post(WEBHOOK, headers=headers[1:]).status_code == 204


def test_no_token_in_the_environment_lets_nobody_in(test_url: str) -> None:
    """Twin EMPTY: no ``SERVICE_TOKEN`` -- not "empty equals empty": 401."""
    given = Settings.model_validate(
        {
            "EDITION": "core",
            "PRIMER_RELEASE": RELEASE,
            "PRIMER_COMMIT": COMMIT,
            **{**SERVICE_SEAMS, "SERVICE_TOKEN": ""},
        }
    )
    for client in client_for(create_app(given, test_url)):
        for authorization in ("Bearer ", "Bearer x", f"Bearer {TOKEN}"):
            response = client.post(WEBHOOK, headers={"Authorization": authorization})
            assert response.status_code == 401, authorization


def test_the_token_never_reaches_the_log(
    client_at_head: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client_at_head.post(WEBHOOK, headers={"Authorization": f"Bearer {TOKEN}"})
    client_at_head.post(WEBHOOK, headers={"Authorization": f"Bearer {TOKEN}x"})
    assert TOKEN not in caplog.text
