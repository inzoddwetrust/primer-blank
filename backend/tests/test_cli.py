"""The verbs of the project: ``python -m app.cli``."""

import os
import subprocess
import sys

from tests.conftest import BACKEND, COMMIT, RELEASE, query_scalar


def _cli(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "PRIMER_RELEASE": RELEASE,
        "PRIMER_COMMIT": COMMIT,
    }
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_set_setting_writes_the_row_and_again_over_it(migrated_db: str) -> None:
    first = _cli(migrated_db, "set-setting", "colour", "blue")
    assert first.returncode == 0, first.stderr
    sql = "SELECT value FROM app_settings WHERE key = 'colour'"
    assert query_scalar(migrated_db, sql) == "blue"
    again = _cli(migrated_db, "set-setting", "colour", "green")
    assert again.returncode == 0, again.stderr
    assert query_scalar(migrated_db, sql) == "green"
    assert query_scalar(migrated_db, "SELECT count(*) FROM app_settings") == 1


def test_a_missing_argument_or_verb_is_refused_before_anything_runs(
    migrated_db: str,
) -> None:
    for args in (("set-setting", "colour"), ("wipe",), ()):
        result = _cli(migrated_db, *args)
        assert result.returncode == 2, (args, result.stderr)
    assert query_scalar(migrated_db, "SELECT count(*) FROM app_settings") == 0
