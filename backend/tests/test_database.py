"""Migrations from a clean database and the bootstrap seed."""

import os
import subprocess
import sys

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.database import ALEMBIC_INI, script_head
from tests.conftest import BACKEND, COMMIT, RELEASE, alembic_config, query_scalar


def test_migrations_have_one_head() -> None:
    heads = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()
    assert heads == [script_head()]


def test_a_clean_database_migrates_to_the_head_and_again(clean_db: str) -> None:
    command.upgrade(alembic_config(), "head")
    command.upgrade(alembic_config(), "head")
    assert query_scalar(clean_db, "SELECT version_num FROM alembic_version") == (
        script_head()
    )
    assert query_scalar(clean_db, "SELECT to_regclass('app_settings')") is not None


def _seed(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "PRIMER_RELEASE": RELEASE,
        "PRIMER_COMMIT": COMMIT,
    }
    return subprocess.run(
        [sys.executable, "-m", "app.seed", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_bootstrap_writes_once(migrated_db: str) -> None:
    first = _seed(migrated_db, "bootstrap")
    assert first.returncode == 0, first.stderr
    at = query_scalar(
        migrated_db, "SELECT value FROM app_settings WHERE key = 'installed_at'"
    )
    assert isinstance(at, str)
    assert at
    second = _seed(migrated_db, "bootstrap")
    assert second.returncode == 0, second.stderr
    assert query_scalar(migrated_db, "SELECT count(*) FROM app_settings") == 1
    assert (
        query_scalar(
            migrated_db, "SELECT value FROM app_settings WHERE key = 'installed_at'"
        )
        == at
    )


def test_bootstrap_on_an_unmigrated_database_fails_loudly(clean_db: str) -> None:
    result = _seed(clean_db, "bootstrap")
    assert result.returncode != 0
    assert "app_settings" in result.stderr


def test_an_unknown_profile_is_refused_before_anything_runs(clean_db: str) -> None:
    result = _seed(clean_db, "demo")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
