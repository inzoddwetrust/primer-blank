"""Images built once per probe session, removed at its end."""

from collections.abc import Iterator

import pytest

from probes.docker import build, docker, remove_labelled

RELEASE = "v0.0.0-probe"
COMMIT = "fedcba9876543210fedcba9876543210fedcba98"
BUILD_ARGS = {"PRIMER_RELEASE": RELEASE, "PRIMER_COMMIT": COMMIT}

BACKEND_RUNTIME = "blank-probe/backend:runtime"
BACKEND_TEST = "blank-probe/backend:test"
FRONTEND_RUNTIME = "blank-probe/frontend:runtime"


@pytest.fixture(scope="session")
def daemon() -> Iterator[None]:
    """A docker daemon, or the session errors: these probes have no other color."""
    docker("version")
    yield
    remove_labelled()


def _built(context: str, tag: str, target: str, args: dict[str, str]) -> str:
    result = build(context, tag, target, args)
    assert result.returncode == 0, result.stderr
    return tag


@pytest.fixture(scope="session")
def backend_runtime(daemon: None) -> str:
    return _built("backend", BACKEND_RUNTIME, "runtime", BUILD_ARGS)


@pytest.fixture(scope="session")
def backend_test(daemon: None) -> str:
    return _built("backend", BACKEND_TEST, "test", BUILD_ARGS)


@pytest.fixture(scope="session")
def frontend_runtime(daemon: None) -> str:
    return _built("frontend", FRONTEND_RUNTIME, "runtime", BUILD_ARGS)
