"""Database engine and explicit session-scope helpers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from paper_knowledge_base.storage.models import Base

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///:memory:"


def database_url_from_env() -> str:
    """Return ``DATABASE_URL`` or a safe ephemeral SQLite default."""

    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_database_engine(
    database_url: str | None = None,
    *,
    echo: bool = False,
    **kwargs: Any,
) -> Engine:
    """Create an engine without opening a global application connection."""

    engine = create_engine(
        database_url or database_url_from_env(),
        future=True,
        echo=echo,
        **kwargs,
    )
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build an explicit synchronous Session factory."""

    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit on success, roll back on every exception, and always close."""

    session = session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def create_schema_for_tests(engine: Engine) -> None:
    """Create tables for isolated tests; production uses Alembic migrations."""

    Base.metadata.create_all(engine)
