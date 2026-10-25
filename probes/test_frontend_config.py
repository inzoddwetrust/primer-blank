"""The frontend's configuration comes from the container's environment."""

import json

from probes.docker import ROOT, docker, run_detached, wait_exit, wait_http


def test_probe_DM_26_frontend_config_is_runtime_not_build_arg(
    frontend_runtime: str,
) -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert [
        line
        for line in dockerfile.splitlines()
        if line.strip().upper().startswith("ARG")
    ] == []

    # One image, two instances: each serves the origin of its own host.
    seen = {}
    for host in ("api.alpha.test", "api.beta.test"):
        container = run_detached(frontend_runtime, {"API_BASE_URL": host})
        status, body = wait_http(container, "/config.json")
        assert status == 200
        seen[host] = json.loads(body)
    assert seen == {
        "api.alpha.test": {"apiBaseUrl": "https://api.alpha.test"},
        "api.beta.test": {"apiBaseUrl": "https://api.beta.test"},
    }


def test_frontend_without_api_base_url_does_not_start(frontend_runtime: str) -> None:
    container = run_detached(frontend_runtime, {})
    assert wait_exit(container) != 0
    logs = docker("logs", container)
    assert "api_base_url" in (logs.stdout + logs.stderr).lower()

    # The pair: the same image with the variable comes up and serves the page.
    up = run_detached(frontend_runtime, {"API_BASE_URL": "api.gamma.test"})
    status, body = wait_http(up, "/some/route")
    assert status == 200
    assert b'<div id="app">' in body
    status, _ = wait_http(up, "/assets/missing.js")
    assert status == 404
