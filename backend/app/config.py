"""Settings of the running backend, read from the environment at start.

Every variable is required and non-empty; a missing or unknown one stops the
start with its name. ``PRIMER_RELEASE`` and ``PRIMER_COMMIT`` are build
arguments the image turns into its environment (contract 3 rule 19).
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.editions import EDITIONS


class Settings(BaseSettings):
    """The environment of the app container."""

    model_config = SettingsConfigDict(populate_by_name=True, extra="ignore")

    edition: str = Field(validation_alias="EDITION", min_length=1)
    release: str = Field(validation_alias="PRIMER_RELEASE", min_length=1)
    commit: str = Field(validation_alias="PRIMER_COMMIT", min_length=1)

    @field_validator("edition")
    @classmethod
    def _known_edition(cls, value: str) -> str:
        if value not in EDITIONS:
            raise ValueError(
                f"EDITION {value!r} is not one of {sorted(EDITIONS)} of this backend"
            )
        return value
