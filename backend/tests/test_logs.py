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

from primer_report import JsonFormatter
from tests.conftest import BACKEND, COMMIT, RELEASE

# TZ section 11, written out here and not imported from primer_report.
FIELDS = ["ts", "level", "service", "release", "request_id", "event", "msg"]

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
