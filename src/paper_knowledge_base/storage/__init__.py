"""Persistent storage boundary for papers, documents, and relationships."""

from paper_knowledge_base.storage.database import (
    create_database_engine,
    create_schema_for_tests,
    create_session_factory,
    database_url_from_env,
    session_scope,
)
from paper_knowledge_base.storage.models import (
    Author,
    Base,
    Document,
    DocumentRole,
    Paper,
    PaperAuthor,
    PaperDocument,
    PaperRelation,
    PaperRelationType,
)
from paper_knowledge_base.storage.service import (
    PaperStorageService,
    PersistenceResult,
    persist_paper_result,
)

__all__ = [
    "Author",
    "Base",
    "Document",
    "DocumentRole",
    "Paper",
    "PaperAuthor",
    "PaperDocument",
    "PaperRelation",
    "PaperRelationType",
    "PaperStorageService",
    "PersistenceResult",
    "create_database_engine",
    "create_schema_for_tests",
    "create_session_factory",
    "database_url_from_env",
    "persist_paper_result",
    "session_scope",
]
