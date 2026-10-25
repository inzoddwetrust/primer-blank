"""The backend refuses to start on a missing or unknown environment."""

import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.conftest import COMMIT, RELEASE

GOOD = {"EDITION": "core", "PRIMER_RELEASE": RELEASE, "PRIMER_COMMIT": COMMIT}


def test_the_environment_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in GOOD.items():
        monkeypatch.setenv(name, value)
    settings = Settings()
    assert (settings.edition, settings.release, settings.commit) == (
        "core",
        RELEASE,
        COMMIT,
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EDITION", "school"),
        ("EDITION", ""),
        ("PRIMER_RELEASE", ""),
        ("PRIMER_COMMIT", ""),
    ],
)
def test_an_unknown_or_empty_value_names_its_variable(name: str, value: str) -> None:
    with pytest.raises(ValidationError, match=name):
        Settings.model_validate({**GOOD, name: value})


@pytest.mark.parametrize("name", sorted(GOOD))
def test_a_missing_variable_is_named(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for other, value in GOOD.items():
        if other == name:
            monkeypatch.delenv(other, raising=False)
        else:
            monkeypatch.setenv(other, value)
    with pytest.raises(ValidationError, match=name):
        Settings()
