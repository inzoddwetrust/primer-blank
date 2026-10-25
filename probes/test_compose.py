"""The compose file refuses to run with any variable of the stack missing."""

from pathlib import Path

from probes.docker import ROOT, docker

STACK_ENV = {
    "POSTGRES_PASSWORD": "probe-password",
    "EDITION": "core",
    "API_BASE_URL": "api.probe.test",
}


def _config(env_file: Path) -> tuple[int, str]:
    result = docker(
        "compose",
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-p",
        "blank-probe",
        "--env-file",
        str(env_file),
        "config",
        "-q",
        check=False,
    )
    return result.returncode, result.stderr


def test_compose_needs_every_variable_of_the_stack(
    daemon: None, tmp_path: Path
) -> None:
    full = tmp_path / "full.env"
    full.write_text("".join(f"{k}={v}\n" for k, v in STACK_ENV.items()))
    assert _config(full) == (0, "")
    for missing in STACK_ENV:
        partial = tmp_path / f"without-{missing}.env"
        partial.write_text(
            "".join(f"{k}={v}\n" for k, v in STACK_ENV.items() if k != missing)
        )
        code, err = _config(partial)
        assert code != 0
        assert missing in err
