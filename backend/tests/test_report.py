"""``PrimerReport`` for any stack: checks under a timeout, ``details``, refusals.

These build a report of stand-in checks -- no database -- and read it over
HTTP, as the machine does.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Mapping

import pytest
from fastapi import FastAPI
from pydantic import JsonValue, ValidationError
from starlette.types import ASGIApp

from primer_report import DETAILS_LIMIT, Health, Limits, PrimerReport, Seams
from tests.conftest import (
    COMMIT,
    PROTOCOL_CHECK_TIMEOUT_S,
    RELEASE,
    client_for,
    report_app,
)

# Longer than any timeout of protocol 9.5, short enough to end the test if a
# check is awaited to the end.
HANG_S = 10.0

Builder = Callable[[], Mapping[str, JsonValue]]


async def ok() -> bool:
    return True


async def hang() -> bool:
    await asyncio.sleep(HANG_S)
    return True


async def boom() -> bool:
    raise ConnectionError("redis: connection refused")


async def false() -> bool:
    return False


async def revision() -> str:
    return "0001"


def builder(value: object) -> Builder:
    """A ``details`` builder that returns ``value``, whatever its type."""

    def build() -> Mapping[str, JsonValue]:
        return value  # type: ignore[return-value]

    return build


def health_of(app: ASGIApp) -> dict[str, object]:
    for client in client_for(app):
        response = client.get("/health")
        assert response.status_code == 200
        body: dict[str, object] = response.json()
        return body
    raise AssertionError("the client did not start")


def refusals(caplog: pytest.LogCaptureFixture) -> list[object]:
    return [
        r.__dict__["ctx"]
        for r in caplog.records
        if r.__dict__.get("event") == "health.details_refused"
    ]


# --- checks -------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", None], ids=["empty", "none"])
def test_a_db_reader_that_gives_no_revision_is_db_error(value: object) -> None:
    """Twin EMPTY of the report: no revision read is ``db: error``, whatever
    the reader gives instead of raising."""

    async def reader() -> str:
        return value  # type: ignore[return-value]

    body = health_of(report_app(reader, head="0001"))
    assert body["checks"] == {"db": "error", "schema": "error"}
    assert body["alembic_head"] is None


def test_a_check_that_raises_is_error_and_health_is_200() -> None:
    body = health_of(report_app(checks={"redis": boom, "queue": ok}))
    assert body["checks"] == {"redis": "error", "queue": "ok"}
    assert body["status"] == "degraded"


def test_a_check_that_says_false_is_error() -> None:
    body = health_of(report_app(checks={"redis": false}))
    assert body["checks"] == {"redis": "error"}


def test_hanging_checks_are_measured_at_once() -> None:
    """Two hang: together they take one timeout, not two."""
    app = report_app(checks={"a": hang, "b": hang, "c": ok})
    for client in client_for(app):
        started = time.monotonic()
        body = client.get("/health").json()
        elapsed = time.monotonic() - started
        assert body["checks"] == {"a": "error", "b": "error", "c": "ok"}
        assert elapsed < 1.5 * PROTOCOL_CHECK_TIMEOUT_S


def test_ready_fails_the_checks_health_reports_not_ok() -> None:
    app = report_app(revision, head="0002", checks={"redis": boom, "queue": ok})
    for client in client_for(app):
        checks = client.get("/health").json()["checks"]
        assert checks == {
            "db": "ok",
            "schema": "error",
            "redis": "error",
            "queue": "ok",
        }
        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json() == {"status": "not_ready", "failing": ["redis", "schema"]}


def test_a_check_turning_to_error_is_logged_once_per_turn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Twin REPEAT: the same failure again is not a new line; after ``ok``
    it is. The line names the class of what stopped it, not its text."""
    state = {"up": False}

    async def toggled() -> bool:
        if state["up"]:
            return True
        raise ConnectionError("password=hunter2 refused")

    caplog.set_level(logging.WARNING, logger="primer_report.health")
    for client in client_for(report_app(checks={"redis": toggled})):
        client.get("/health")
        client.get("/ready")
        state["up"] = True
        client.get("/health")
        state["up"] = False
        client.get("/health")
    failed = [
        r for r in caplog.records if r.__dict__.get("event") == "health.check_failed"
    ]
    assert [r.__dict__["ctx"] for r in failed] == [
        {"check": "redis", "error": "ConnectionError"},
        {"check": "redis", "error": "ConnectionError"},
    ]
    assert all("hunter2" not in r.getMessage() for r in failed)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({}, "at least one check"),
        ({"head_checks": {"schema": lambda _: True}}, "need db"),
        ({"db": revision, "checks": {"db": ok}}, "repeat"),
        ({"db": revision, "head_checks": {"x": bool}, "checks": {"x": ok}}, "repeat"),
    ],
    ids=["no-checks", "head-without-db", "db-twice", "name-twice"],
)
def test_a_report_with_no_or_repeated_checks_is_refused(
    kwargs: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        PrimerReport(
            service="blank",
            release=RELEASE,
            commit=COMMIT,
            edition="core",
            modules=[],
            limits=Limits(max_upload_mb=1),
            seams=Seams(provides=[], requires_satisfied=True),
            **kwargs,  # type: ignore[arg-type]
        )


def test_a_wrong_fixed_field_fails_the_start_not_a_request() -> None:
    with pytest.raises(ValidationError, match="service"):
        PrimerReport(
            service="",
            release=RELEASE,
            commit=COMMIT,
            edition="core",
            modules=[],
            limits=Limits(max_upload_mb=1),
            seams=Seams(provides=[], requires_satisfied=True),
            checks={"redis": ok},
        )


# --- details ------------------------------------------------------------------


def _sized(size: int) -> dict[str, JsonValue]:
    """``{"x": <text>}`` of ``size`` bytes, two-byte letters in it: the size
    the machine measures (compact, not ASCII-escaped) and no other."""
    letters = "й" * 100
    rest = size - len('{"x":""}') - len(letters.encode())
    return {"x": letters + "a" * rest}


def test_no_details_leaves_the_key_out(caplog: pytest.LogCaptureFixture) -> None:
    body = health_of(report_app(checks={"redis": ok}))
    assert "details" not in body
    assert refusals(caplog) == []


def test_empty_details_are_sent() -> None:
    """Twin EMPTY: ``{}`` is an object of the stack -- sent as it is."""
    body = health_of(report_app(checks={"redis": ok}, details=builder({})))
    assert body["details"] == {}


def test_details_of_exactly_the_limit_are_sent() -> None:
    value = _sized(DETAILS_LIMIT)
    body = health_of(report_app(checks={"redis": ok}, details=builder(value)))
    assert body["details"] == value
    Health.model_validate(body)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (_sized(DETAILS_LIMIT + 1), {"reason": "size", "size": DETAILS_LIMIT + 1}),
        ([1, 2], {"reason": "type"}),
        ("text", {"reason": "type"}),
        ({"when": {1, 2}}, {"reason": "type"}),
        ({1: "x"}, {"reason": "type"}),
    ],
    ids=["one-byte-over", "list", "text", "not-json-inside", "key-not-text"],
)
def test_details_that_cannot_be_sent_are_left_out_and_named(
    value: object, reason: dict[str, object], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="primer_report.health")
    body = health_of(report_app(checks={"redis": ok}, details=builder(value)))
    assert "details" not in body
    assert body["status"] == "ok"
    assert refusals(caplog) == [reason]


def test_a_failing_details_builder_leaves_details_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def build() -> Mapping[str, JsonValue]:
        raise KeyError("x")

    caplog.set_level(logging.WARNING, logger="primer_report.health")
    body = health_of(report_app(checks={"redis": ok}, details=build))
    assert "details" not in body
    assert refusals(caplog) == [{"reason": "error", "error": "KeyError"}]


def test_the_health_model_refuses_details_of_null_or_over_the_limit() -> None:
    body = health_of(report_app(checks={"redis": ok}))
    with pytest.raises(ValidationError, match="details"):
        Health.model_validate({**body, "details": None})
    with pytest.raises(ValidationError, match="over"):
        Health.model_validate({**body, "details": _sized(DETAILS_LIMIT + 1)})


def test_a_head_check_that_raises_is_error_and_health_is_200() -> None:
    def judge(revision: str) -> bool:
        raise ValueError(revision)

    app = PrimerReport(
        service="blank",
        release=RELEASE,
        commit=COMMIT,
        edition="core",
        modules=[],
        limits=Limits(max_upload_mb=1),
        seams=Seams(provides=[], requires_satisfied=True),
        db=revision,
        head_checks={"schema": judge},
    ).install(FastAPI())
    body = health_of(app)
    assert body["checks"] == {"db": "ok", "schema": "error"}
    assert body["alembic_head"] == "0001"
