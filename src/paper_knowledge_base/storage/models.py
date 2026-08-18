"""SQLAlchemy ORM models for persistent paper storage.

These classes are intentionally confined to ``storage``. Processing, metadata,
and identity code continues to use its parser-independent domain models.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    """Declarative base for the storage schema."""


def utc_now() -> datetime:
    """Return an aware UTC timestamp for application-side defaults."""

    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC timestamps portably and always return aware datetimes.

    SQLite does not preserve timezone offsets for its datetime affinity. Values
    are therefore stored as naive UTC on SQLite and reattached to UTC when read
    back. PostgreSQL uses its timezone-aware timestamp type directly.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        return dialect.type_descriptor(DateTime(timezone=dialect.name == "postgresql"))

    def process_bind_param(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("storage timestamps must be timezone-aware")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )


class DocumentRole(str, Enum):
    UNKNOWN = "unknown"
    PUBLISHER_VERSION = "publisher_version"
    AUTHOR_MANUSCRIPT = "author_manuscript"
    PREPRINT_COPY = "preprint_copy"
    REPOSITORY_COPY = "repository_copy"
    OCR_DERIVED = "ocr_derived"
    OTHER = "other"


class PaperRelationType(str, Enum):
    VERSION_OF = "version_of"
    CORRECTION_OF = "correction_of"
    RETRACTION_OF = "retraction_of"
    SUPPLEMENT_OF = "supplement_of"
    RELATED_TO = "related_to"


class Paper(TimestampMixin, Base):
    __tablename__ = "papers"
    __table_args__ = (
        Index("ix_papers_normalized_title", "normalized_title"),
        Index("ix_papers_publication_year", "publication_year"),
        Index("ix_papers_doi", "doi"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_title: Mapped[str | None] = mapped_column(String(2000))
    normalized_title: Mapped[str | None] = mapped_column(String(2000))
    doi: Mapped[str | None] = mapped_column(String(512), unique=True)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    venue_name: Mapped[str | None] = mapped_column(String(1000))
    publisher: Mapped[str | None] = mapped_column(String(1000))
    volume: Mapped[str | None] = mapped_column(String(100))
    issue: Mapped[str | None] = mapped_column(String(100))
    pages: Mapped[str | None] = mapped_column(String(200))
    work_type: Mapped[str | None] = mapped_column(String(100))
    canonical_confidence: Mapped[str | None] = mapped_column(String(32))
    metadata_provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    metadata_evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    metadata_conflicts_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )

    documents: Mapped[list[PaperDocument]] = relationship(
        back_populates="paper", passive_deletes=True
    )
    source_relations: Mapped[list[PaperRelation]] = relationship(
        foreign_keys="PaperRelation.source_paper_id",
        back_populates="source_paper",
        passive_deletes=True,
    )
    target_relations: Mapped[list[PaperRelation]] = relationship(
        foreign_keys="PaperRelation.target_paper_id",
        back_populates="target_paper",
        passive_deletes=True,
    )
    authors: Mapped[list[PaperAuthor]] = relationship(
        back_populates="paper", passive_deletes=True
    )


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_sha256", "sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    filename: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown"
    )
    source_identifier: Mapped[str | None] = mapped_column(String(1000))
    source_uri: Mapped[str | None] = mapped_column(String(2000))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    has_embedded_text: Mapped[bool | None] = mapped_column(Boolean)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    processing_status: Mapped[str | None] = mapped_column(String(32))
    processing_route: Mapped[str | None] = mapped_column(String(32))
    processing_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    paper_document: Mapped[PaperDocument | None] = relationship(
        back_populates="document", uselist=False, passive_deletes=True
    )


class PaperDocument(TimestampMixin, Base):
    __tablename__ = "paper_documents"
    __table_args__ = (
        UniqueConstraint("paper_id", "document_id", name="uq_paper_documents_pair"),
        UniqueConstraint("document_id", name="uq_paper_documents_one_paper"),
        Index("ix_paper_documents_paper_id", "paper_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("papers.id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocumentRole.UNKNOWN.value
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    paper: Mapped[Paper] = relationship(back_populates="documents")
    document: Mapped[Document] = relationship(back_populates="paper_document")


class PaperRelation(TimestampMixin, Base):
    __tablename__ = "paper_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_paper_id",
            "target_paper_id",
            "relation_type",
            name="uq_paper_relations_edge",
        ),
        CheckConstraint(
            "source_paper_id <> target_paper_id", name="ck_paper_relations_not_self"
        ),
        Index("ix_paper_relations_source", "source_paper_id"),
        Index("ix_paper_relations_target", "target_paper_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_paper_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_paper_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(32))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    source_paper: Mapped[Paper] = relationship(
        foreign_keys=[source_paper_id], back_populates="source_relations"
    )
    target_paper: Mapped[Paper] = relationship(
        foreign_keys=[target_paper_id], back_populates="target_relations"
    )


class Author(TimestampMixin, Base):
    __tablename__ = "authors"
    __table_args__ = (Index("ix_authors_normalized_name", "normalized_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    given_name: Mapped[str | None] = mapped_column(String(300))
    family_name: Mapped[str | None] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)

    papers: Mapped[list[PaperAuthor]] = relationship(
        back_populates="author", passive_deletes=True
    )


class PaperAuthor(TimestampMixin, Base):
    __tablename__ = "paper_authors"
    __table_args__ = (
        UniqueConstraint("paper_id", "author_id", name="uq_paper_authors_pair"),
        UniqueConstraint(
            "paper_id", "author_position", name="uq_paper_authors_position"
        ),
        Index("ix_paper_authors_paper_id", "paper_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("papers.id", ondelete="RESTRICT"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("authors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    author_position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_corresponding: Mapped[bool | None] = mapped_column(Boolean)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    paper: Mapped[Paper] = relationship(back_populates="authors")
    author: Mapped[Author] = relationship(back_populates="papers")
