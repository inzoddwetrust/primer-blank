"""Log lines of the running server: JSON, fixed fields, the request id."""

import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import script_head
from primer_report import JsonFormatter
from tests.conftest import BACKEND, COMMIT, RELEASE

# Protocol 9.4, written out here and not imported from primer_report.
FIELDS = ["ts", "level", "service", "release", "request_id", "event", "msg"]
CTX = "ctx"

LEVELS = {"debug", "info", "warning", "error", "critical"}
GENERATED_ID = re.compile(r"^[0-9a-f]{32}$")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def _serve_and_log(
    database_url: str, requests: list[dict[str, str]]
) -> tuple[list[str], str, list[str]]:
    """Run the image's server command, send ``requests``, stop it.

    Returns stdout lines, stderr and the response request ids. Output is read
    only after the process exits, so buffering cannot reorder or lose it; the
    child gets no PYTHONUNBUFFERED, as on the runner.
    """
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
    env.update(
        DATABASE_URL=database_url,
        EDITION="core",
        PRIMER_RELEASE=RELEASE,
        PRIMER_COMMIT=COMMIT,
    )
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "--factory",
            "app.main:create_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-config",
            "logging.json",
        ],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ids: list[str] = []
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                httpx.get(f"http://127.0.0.1:{port}/ready", timeout=1)
                break
            except httpx.TransportError:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise
                time.sleep(0.1)
        for headers in requests:
            response = httpx.get(
                f"http://127.0.0.1:{port}/health", headers=headers, timeout=10
            )
            ids.append(response.headers["x-request-id"])
    finally:
        proc.terminate()
        out, err = proc.communicate(timeout=20)
    return out.splitlines(), err, ids


def test_probe_DM_26_logs_are_json_with_fixed_fields(unreachable_url: str) -> None:
    """Every line: the seven fields of protocol 9.4 and, given, ``ctx`` last.

    Changed by DM-66 (protocol 9.1/9.4 v1.7: the optional ``details``,
    ``ctx``; 9.5: a revision that is not read is ``db: error``): a line may
    carry ``ctx``, checked apart from the seven -- an object; ``app.started``
    carries the edition and the migrations' head.
    """
    sent = [
        {},
        {"X-Request-ID": "probe-26.a_b"},
        {"X-Request-ID": ""},
        {"X-Request-ID": "has space"},
        {"X-Request-ID": "x" * 129},
    ]
    lines, err, ids = _serve_and_log(unreachable_url, sent)

    assert err == ""
    assert lines
    records = [json.loads(line) for line in lines]
    for record in records:
        if CTX in record:
            assert list(record) == [*FIELDS, CTX]
            assert isinstance(record[CTX], dict)
        else:
            assert list(record) == FIELDS
        assert record["level"] in LEVELS
        assert record["service"] == "blank"
        assert record["release"] == RELEASE
        assert isinstance(record["event"], str)
        assert record["event"]
        assert isinstance(record["msg"], str)
        datetime.fromisoformat(record["ts"])

    started = [r for r in records if r["event"] == "app.started"]
    assert len(started) == 1
    assert started[0]["request_id"] is None
    assert started[0][CTX] == {"edition": "core", "script_head": script_head()}

    access = [
        r for r in records if r["event"] == "uvicorn.access" and "/health" in r["msg"]
    ]
    assert [r["request_id"] for r in access] == ids
    assert ids[1] == "probe-26.a_b"
    for generated in (ids[0], ids[2], ids[3], ids[4]):
        assert GENERATED_ID.fullmatch(generated)
    assert len(set(ids)) == len(ids)


def test_a_traceback_stays_inside_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIMER_RELEASE", RELEASE)
    formatter = JsonFormatter(service="blank")
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.getLogger("t").makeRecord(
            "t", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )
    line = formatter.format(record)
    assert "\n" not in line
    parsed = json.loads(line)
    assert list(parsed) == FIELDS
    assert "ValueError: boom" in parsed["msg"]
    assert parsed["event"] == "t"


def test_the_formatter_refuses_to_start_without_a_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PRIMER_RELEASE", raising=False)
    with pytest.raises(RuntimeError, match="PRIMER_RELEASE"):
        JsonFormatter(service="blank")


def test_of_two_request_id_headers_the_last_one_is_taken(
    client_db_down: TestClient,
) -> None:
    """Twin REPEAT: two headers in one request -- the last one, judged alone."""
    response = client_db_down.get(
        "/health", headers=[("X-Request-ID", "first-id"), ("X-Request-ID", "last-id")]
    )
    assert response.headers.get_list("x-request-id") == ["last-id"]

    response = client_db_down.get(
        "/health", headers=[("X-Request-ID", "first-id"), ("X-Request-ID", "bad id")]
    )
    (taken,) = response.headers.get_list("x-request-id")
    assert GENERATED_ID.fullmatch(taken)


def _line_with(monkeypatch: pytest.MonkeyPatch, **extra: object) -> dict[str, object]:
    monkeypatch.setenv("PRIMER_RELEASE", RELEASE)
    record = logging.getLogger("t").makeRecord(
        "t", logging.INFO, __file__, 1, "done", (), None, extra=extra
    )
    line = JsonFormatter(service="blank").format(record)
    parsed: dict[str, object] = json.loads(line)
    return parsed


def test_a_ctx_object_is_written_last(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = {"job": "7", "sqlstate": "40001", "nested": {"n": [1, 2]}}
    parsed = _line_with(monkeypatch, event="job.failed", ctx=ctx)
    assert list(parsed) == [*FIELDS, CTX]
    assert parsed[CTX] == ctx
    assert parsed["event"] == "job.failed"


def test_no_ctx_leaves_the_seven_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    assert list(_line_with(monkeypatch, event="x")) == FIELDS


@pytest.mark.parametrize(
    "ctx",
    ["job 7", ["job", 7], 7, None, {"when": datetime(2026, 11, 5)}],
    ids=["text", "list", "number", "null", "not-json-inside"],
)
def test_a_ctx_that_is_not_a_json_object_is_left_out(
    ctx: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The line is still written, with its seven fields and no ``ctx``."""
    parsed = _line_with(monkeypatch, event="x", ctx=ctx)
    assert list(parsed) == FIELDS
    assert parsed["msg"] == "done"


def test_an_empty_ctx_is_written_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twin EMPTY: ``{}`` is an object -- written, not dropped."""
    parsed = _line_with(monkeypatch, ctx={})
    assert list(parsed) == [*FIELDS, CTX]
    assert parsed[CTX] == {}


def test_a_ctx_over_8_kb_is_written_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stack does not cut: over 8 KB the deploy machine does (9.4)."""
    ctx = {"tail": "x" * 9 * 1024}
    assert _line_with(monkeypatch, ctx=ctx)[CTX] == ctx
