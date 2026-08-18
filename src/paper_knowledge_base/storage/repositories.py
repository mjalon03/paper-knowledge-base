"""Domain-oriented repository operations for the storage schema."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from paper_knowledge_base.metadata.normalization import normalize_doi
from paper_knowledge_base.storage.models import (
    Author,
    Document,
    DocumentRole,
    Paper,
    PaperAuthor,
    PaperDocument,
    PaperRelation,
)


class DocumentRepository:
    @staticmethod
    def get_by_sha256(session: Session, sha256: str) -> Document | None:
        return session.scalar(select(Document).where(Document.sha256 == sha256))

    @staticmethod
    def get_by_id(session: Session, document_id: uuid.UUID) -> Document | None:
        return session.get(Document, document_id)

    @staticmethod
    def create(
        session: Session,
        *,
        sha256: str,
        filename: str,
        source_type: str = "unknown",
        source_identifier: str | None = None,
        source_uri: str | None = None,
        size_bytes: int | None = None,
        page_count: int | None = None,
        mime_type: str | None = "application/pdf",
        has_embedded_text: bool | None = None,
        processed_at: Any = None,
        processing_status: str | None = None,
        processing_route: str | None = None,
        processing_metadata_json: dict[str, Any] | None = None,
    ) -> Document:
        document = Document(
            sha256=sha256,
            filename=filename,
            source_type=source_type,
            source_identifier=source_identifier,
            source_uri=source_uri,
            size_bytes=size_bytes,
            page_count=page_count,
            mime_type=mime_type,
            has_embedded_text=has_embedded_text,
            processed_at=processed_at,
            processing_status=processing_status,
            processing_route=processing_route,
            processing_metadata_json=processing_metadata_json or {},
        )
        session.add(document)
        session.flush()
        return document

    @classmethod
    def get_or_create_by_sha256(
        cls, session: Session, **values: Any
    ) -> tuple[Document, bool]:
        existing = cls.get_by_sha256(session, values["sha256"])
        if existing is not None:
            return existing, False
        try:
            with session.begin_nested():
                document = cls.create(session, **values)
        except IntegrityError:
            existing = cls.get_by_sha256(session, values["sha256"])
            if existing is None:
                raise
            return existing, False
        return document, True


class PaperRepository:
    @staticmethod
    def get_by_id(session: Session, paper_id: uuid.UUID) -> Paper | None:
        return session.get(Paper, paper_id)

    @staticmethod
    def get_by_doi(session: Session, doi: str | None) -> Paper | None:
        normalized = normalize_doi(doi)
        if normalized is None:
            return None
        return session.scalar(select(Paper).where(Paper.doi == normalized))

    @staticmethod
    def create(session: Session, **values: Any) -> Paper:
        values = dict(values)
        if values.get("doi") is not None:
            values["doi"] = normalize_doi(values["doi"])
        paper = Paper(**values)
        session.add(paper)
        session.flush()
        return paper

    @staticmethod
    def update_canonical(
        session: Session,
        paper: Paper,
        values: dict[str, Any],
        *,
        metadata_evidence_json: list[dict[str, Any]],
        metadata_conflicts_json: list[str],
    ) -> Paper:
        incoming_confidence = _confidence_rank(values.get("canonical_confidence"))
        current_confidence = _confidence_rank(paper.canonical_confidence)
        for key, value in values.items():
            if key == "metadata_provenance_json":
                if value:
                    paper.metadata_provenance_json = value
                continue
            if value is None:
                continue
            current = getattr(paper, key)
            if current is None or incoming_confidence > current_confidence:
                setattr(paper, key, value)
        paper.metadata_evidence_json = [
            *paper.metadata_evidence_json,
            *metadata_evidence_json,
        ]
        paper.metadata_conflicts_json = [
            *paper.metadata_conflicts_json,
            *metadata_conflicts_json,
        ]
        session.flush()
        return paper


class PaperDocumentRepository:
    @staticmethod
    def get_by_pair(
        session: Session, paper_id: uuid.UUID, document_id: uuid.UUID
    ) -> PaperDocument | None:
        return session.scalar(
            select(PaperDocument).where(
                PaperDocument.paper_id == paper_id,
                PaperDocument.document_id == document_id,
            )
        )

    @staticmethod
    def get_by_document(
        session: Session, document_id: uuid.UUID
    ) -> PaperDocument | None:
        return session.scalar(
            select(PaperDocument).where(PaperDocument.document_id == document_id)
        )

    @staticmethod
    def attach(
        session: Session,
        *,
        paper_id: uuid.UUID,
        document_id: uuid.UUID,
        role: DocumentRole = DocumentRole.UNKNOWN,
        is_primary: bool = False,
    ) -> PaperDocument:
        association = PaperDocument(
            paper_id=paper_id,
            document_id=document_id,
            role=role.value,
            is_primary=is_primary,
        )
        session.add(association)
        session.flush()
        return association


class PaperRelationRepository:
    @staticmethod
    def get_by_edge(
        session: Session,
        *,
        source_paper_id: uuid.UUID,
        target_paper_id: uuid.UUID,
        relation_type: str,
    ) -> PaperRelation | None:
        return session.scalar(
            select(PaperRelation).where(
                PaperRelation.source_paper_id == source_paper_id,
                PaperRelation.target_paper_id == target_paper_id,
                PaperRelation.relation_type == relation_type,
            )
        )

    @staticmethod
    def create(
        session: Session,
        *,
        source_paper_id: uuid.UUID,
        target_paper_id: uuid.UUID,
        relation_type: str,
        confidence: str | None,
        evidence_json: dict[str, Any],
    ) -> PaperRelation:
        relation = PaperRelation(
            source_paper_id=source_paper_id,
            target_paper_id=target_paper_id,
            relation_type=relation_type,
            confidence=confidence,
            evidence_json=evidence_json,
        )
        session.add(relation)
        session.flush()
        return relation


class AuthorRepository:
    @staticmethod
    def create(session: Session, **values: Any) -> Author:
        author = Author(**values)
        session.add(author)
        session.flush()
        return author

    @staticmethod
    def attach(
        session: Session,
        *,
        paper_id: uuid.UUID,
        author_id: uuid.UUID,
        author_position: int,
        is_corresponding: bool | None,
        provenance_json: dict[str, Any],
    ) -> PaperAuthor:
        association = PaperAuthor(
            paper_id=paper_id,
            author_id=author_id,
            author_position=author_position,
            is_corresponding=is_corresponding,
            provenance_json=provenance_json,
        )
        session.add(association)
        session.flush()
        return association


def _confidence_rank(value: str | None) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(value or "", 0)
