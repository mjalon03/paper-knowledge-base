from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from paper_knowledge_base.storage.database import create_database_engine

pytestmark = pytest.mark.storage_integration


@pytest.mark.skipif(
    os.environ.get("PKB_RUN_STORAGE_INTEGRATION") != "1"
    or not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="Set PKB_RUN_STORAGE_INTEGRATION=1 with a dedicated PostgreSQL DATABASE_URL.",
)
def test_postgresql_migration_creates_storage_tables() -> None:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(config, "head")
    engine = create_database_engine(os.environ["DATABASE_URL"])
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {"papers", "documents", "paper_documents", "paper_relations"} <= tables
