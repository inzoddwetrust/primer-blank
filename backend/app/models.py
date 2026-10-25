"""Tables of the backend."""

from sqlalchemy import String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base of every ORM model; its metadata is the target of migrations."""


class AppSetting(Base):
    """A key-value setting of the instance; the bootstrap seed writes the first."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
