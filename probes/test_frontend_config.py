"""The frontend's configuration comes from the container's environment."""

import json

import pytest

from probes.docker import ROOT, docker, run_detached, wait_exit, wait_http

INSTANCE = {"LANGUAGES": "en,ru", "DEFAULT_LANGUAGE": "en"}
"""The languages of an instance as the machine renders them (DM-46)."""


def test_probe_DM_26_frontend_config_is_runtime_not_build_arg(
    frontend_runtime: str,
) -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert [
        line
        for line in dockerfile.splitlines()
        if line.strip().upper().startswith("ARG")
    ] == []

    # One image, two instances: each serves its own host and languages.
    seen = {}
    for host, languages, default in (
        ("api.alpha.test", "en", "en"),
        ("api.beta.test", "ru,en", "ru"),
    ):
        env = {
            "API_BASE_URL": host,
            "LANGUAGES": languages,
            "DEFAULT_LANGUAGE": default,
        }
        container = run_detached(frontend_runtime, env)
        status, body = wait_http(container, "/config.json")
        assert status == 200
        seen[host] = json.loads(body)
    assert seen == {
        "api.alpha.test": {
            "apiBaseUrl": "https://api.alpha.test",
            "languages": "en",
            "defaultLanguage": "en",
        },
        "api.beta.test": {
            "apiBaseUrl": "https://api.beta.test",
            "languages": "ru,en",
            "defaultLanguage": "ru",
        },
    }


@pytest.mark.parametrize("missing", ["API_BASE_URL", "LANGUAGES", "DEFAULT_LANGUAGE"])
def test_frontend_without_a_variable_does_not_start(
    frontend_runtime: str, missing: str
) -> None:
    env = {"API_BASE_URL": "api.gamma.test", **INSTANCE}
    env.pop(missing)
    container = run_detached(frontend_runtime, env)
    assert wait_exit(container) != 0
    logs = docker("logs", container)
    assert missing.lower() in (logs.stdout + logs.stderr).lower()

    # The pair: the same image with every variable comes up and serves the page.
    up = run_detached(frontend_runtime, {"API_BASE_URL": "api.gamma.test", **INSTANCE})
    status, body = wait_http(up, "/some/route")
    assert status == 200
    assert b'<div id="app">' in body
    status, _ = wait_http(up, "/assets/missing.js")
    assert status == 404
