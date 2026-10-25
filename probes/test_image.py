"""What the images carry: the runtime has no tests and no documents."""

from pathlib import PurePosixPath

from probes.conftest import BUILD_ARGS, COMMIT, RELEASE
from probes.docker import LABEL, build, docker, image_config, list_files

DOC_SUFFIXES = {".md", ".rst"}


def _has_tests(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1]
    return "tests" in parts or name.startswith("test_") or ".spec." in name


def _is_document(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in DOC_SUFFIXES


def _python_has(image: str, module: str) -> bool:
    out = docker(
        "run",
        "--rm",
        "--label",
        LABEL,
        "--entrypoint",
        "python",
        image,
        "-c",
        "import importlib.util; "
        f"print(importlib.util.find_spec({module!r}) is not None)",
    ).stdout.strip()
    return out == "True"


def test_probe_DM_26_image_excludes_tests_and_docs(
    backend_runtime: str, backend_test: str, frontend_runtime: str
) -> None:
    backend = list_files(backend_runtime, "/app")
    assert [p for p in backend if _has_tests(p)] == []
    assert [p for p in backend if _is_document(p)] == []
    assert not _python_has(backend_runtime, "pytest")
    # ...and the runtime is the application, not an empty directory.
    for needed in (
        "app/main.py",
        "primer_report/health.py",
        "alembic.ini",
        "logging.json",
    ):
        assert needed in backend
    assert [
        p for p in backend if p.startswith("migrations/versions/") and p.endswith(".py")
    ]
    assert _python_has(backend_runtime, "uvicorn")

    # The test stage of primer.yaml (test.target) does carry them.
    tested = list_files(backend_test, "/app")
    assert "tests/conftest.py" in tested
    assert _python_has(backend_test, "pytest")

    frontend = list_files(frontend_runtime, "/usr/share/nginx/html")
    assert [p for p in frontend if _has_tests(p)] == []
    assert [p for p in frontend if _is_document(p)] == []
    assert [p for p in frontend if p.endswith((".ts", ".vue"))] == []
    assert "index.html" in frontend
    assert [p for p in frontend if p.startswith("assets/") and p.endswith(".js")]


def test_the_backend_image_carries_release_commit_and_json_logs(
    backend_runtime: str,
) -> None:
    config = image_config(backend_runtime)
    assert f"PRIMER_RELEASE={RELEASE}" in config["Env"]
    assert f"PRIMER_COMMIT={COMMIT}" in config["Env"]
    cmd = config["Cmd"]
    assert cmd[cmd.index("--log-config") + 1] == "logging.json"


def test_a_build_without_release_or_commit_stops_by_name(daemon: None) -> None:
    for missing in BUILD_ARGS:
        args = {k: v for k, v in BUILD_ARGS.items() if k != missing}
        result = build("backend", "blank-probe/backend:incomplete", "runtime", args)
        assert result.returncode != 0
        assert f"{missing} build argument is not set" in result.stderr
