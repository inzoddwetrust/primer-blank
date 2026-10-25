"""``/health`` and ``/ready`` in every state of the database."""

import time

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.config import Settings
from app.database import script_head
from app.main import MAX_UPLOAD_MB, create_app
from primer_report import Health
from tests.conftest import COMMIT, RELEASE, alembic_config, client_for

# TZ section 11, written out here and not taken from the model: a field the
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

# state -> (status, checks, alembic_head is the head)
EXPECTED = {
    "client_at_head": ("ok", {"db": "ok", "schema": "ok"}, True),
    "client_not_migrated": ("degraded", {"db": "ok", "schema": "error"}, False),
    "client_db_down": ("degraded", {"db": "error", "schema": "error"}, False),
}


@pytest.mark.parametrize("state", sorted(EXPECTED))
def test_probe_DM_26_health_matches_schema_11(
    state: str, request: pytest.FixtureRequest
) -> None:
    client: TestClient = request.getfixturevalue(state)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == FIELDS_11
    Health.model_validate(body)

    status, checks, at_head = EXPECTED[state]
    assert body["status"] == status
    assert body["checks"] == checks
    assert body["alembic_head"] == (script_head() if at_head else None)
    assert body["service"] == "blank"
    assert body["release"] == RELEASE
    assert body["commit"] == COMMIT
    assert type(body["uptime_s"]) is int
    assert body["uptime_s"] >= 0
    assert body["seams"] == {"provides": [], "requires_satisfied": True}
    assert body["limits"] == {"max_upload_mb": MAX_UPLOAD_MB}
    assert body["edition"] == "core"
    assert body["modules"] == []


@pytest.mark.parametrize(
    ("state", "code", "failing"),
    [
        ("client_at_head", 200, []),
        ("client_not_migrated", 503, ["schema"]),
        ("client_db_down", 503, ["db", "schema"]),
    ],
)
def test_ready_only_at_head(
    state: str, code: int, failing: list[str], request: pytest.FixtureRequest
) -> None:
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
    test_url: str, settings: Settings
) -> None:
    """A host that drops packets is given up on, not waited for."""
    silent = (
        make_url(test_url)
        .set(host="10.255.255.1")
        .render_as_string(hide_password=False)
    )
    for client in client_for(create_app(settings, silent)):
        started = time.monotonic()
        body = client.get("/health").json()
        elapsed = time.monotonic() - started
        assert body["checks"]["db"] == "error"
        assert elapsed < 6


def test_the_health_model_is_closed(client_at_head: TestClient) -> None:
    """The model the probe validates with refuses a field TZ 11 does not name."""
    body = client_at_head.get("/health").json()
    with pytest.raises(ValidationError, match="extra"):
        Health.model_validate({**body, "version": "x"})
    with pytest.raises(ValidationError, match="extra"):
        Health.model_validate({**body, "limits": {"max_upload_mb": 1, "x": 2}})
