"""Persistence orchestration that consumes existing domain decisions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from paper_knowledge_base.identity.models import IdentityDecision, IdentityRelationship
from paper_knowledge_base.metadata.models import ResolutionResult
from paper_knowledge_base.processing.models import PaperProcessingResult
from paper_knowledge_base.storage.mappers import (
    canonical_authors,
    canonical_paper_values,
    identity_to_json,
    processing_to_json,
    resolution_to_json,
)
from paper_knowledge_base.storage.models import (
    DocumentRole,
    Paper,
    PaperRelationType,
)
from paper_knowledge_base.storage.repositories import (
    AuthorRepository,
    DocumentRepository,
    PaperDocumentRepository,
    PaperRelationRepository,
    PaperRepository,
)


@dataclass(frozen=True)
class PersistenceResult:
    """Stable IDs and actions returned to ingestion/orchestration code."""

    action: str
    paper_id: uuid.UUID
    document_id: uuid.UUID
    paper_document_id: uuid.UUID | None
    relation_id: uuid.UUID | None
    paper_created: bool
    document_created: bool


class PaperStorageService:
    """Persist processing and resolution outputs inside a caller-owned session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def persist_paper_result(
        self,
        *,
        processing_result: PaperProcessingResult,
        resolution_result: ResolutionResult,
        identity_decision: IdentityDecision | None = None,
        existing_paper_id: uuid.UUID | None = None,
        related_paper_id: uuid.UUID | None = None,
        document_role: DocumentRole = DocumentRole.UNKNOWN,
        source_type: str = "local",
        source_identifier: str | None = None,
        source_uri: str | None = None,
    ) -> PersistenceResult:
        """Persist one pipeline result without performing identity matching.

        ``existing_paper_id`` is required for an explicit SAME_PAPER decision
        when DOI lookup cannot safely identify the existing Paper. Related
        version/material decisions create a new Paper and require
        ``related_paper_id`` so the relation direction is explicit.
        """

        document, document_created = DocumentRepository.get_or_create_by_sha256(
            self.session,
            sha256=processing_result.file.sha256,
            filename=processing_result.file.filename,
            source_type=source_type,
            source_identifier=source_identifier or processing_result.file.filename,
            source_uri=source_uri,
            size_bytes=processing_result.file.size_bytes,
            page_count=processing_result.inspection.page_count,
            mime_type="application/pdf",
            has_embedded_text=processing_result.inspection.has_usable_embedded_text,
            processed_at=_processed_at(processing_result),
            processing_status=processing_result.status.value,
            processing_route=processing_result.route.value,
            processing_metadata_json=processing_to_json(processing_result),
        )

        existing_association = PaperDocumentRepository.get_by_document(
            self.session, document.id
        )
        if not document_created and existing_association is not None:
            return PersistenceResult(
                action="reused_document",
                paper_id=existing_association.paper_id,
                document_id=document.id,
                paper_document_id=existing_association.id,
                relation_id=None,
                paper_created=False,
                document_created=False,
            )

        paper, paper_created, relation_target = self._select_paper(
            resolution_result,
            identity_decision=identity_decision,
            existing_paper_id=existing_paper_id,
            related_paper_id=related_paper_id,
        )
        if paper_created:
            self._populate_new_paper(paper, resolution_result)
        else:
            PaperRepository.update_canonical(
                self.session,
                paper,
                canonical_paper_values(resolution_result),
                metadata_evidence_json=[resolution_to_json(resolution_result)],
                metadata_conflicts_json=list(resolution_result.conflicts),
            )

        self._persist_authors(paper, resolution_result)
        association = PaperDocumentRepository.attach(
            self.session,
            paper_id=paper.id,
            document_id=document.id,
            role=document_role,
            is_primary=paper_created,
        )
        relation = None
        if relation_target is not None and identity_decision is not None:
            relation = PaperRelationRepository.create(
                self.session,
                source_paper_id=paper.id,
                target_paper_id=relation_target,
                relation_type=_relation_type(identity_decision.relationship).value,
                confidence=identity_decision.confidence.value,
                evidence_json=identity_to_json(identity_decision),
            )
        action = _action_for(
            identity_decision, paper_created, document_created, relation
        )
        return PersistenceResult(
            action=action,
            paper_id=paper.id,
            document_id=document.id,
            paper_document_id=association.id,
            relation_id=relation.id if relation is not None else None,
            paper_created=paper_created,
            document_created=document_created,
        )

    def _select_paper(
        self,
        resolution_result: ResolutionResult,
        *,
        identity_decision: IdentityDecision | None,
        existing_paper_id: uuid.UUID | None,
        related_paper_id: uuid.UUID | None,
    ) -> tuple[Paper, bool, uuid.UUID | None]:
        relationship = (
            identity_decision.relationship if identity_decision is not None else None
        )
        if relationship == IdentityRelationship.SAME_PAPER:
            paper = self._existing_paper(existing_paper_id, resolution_result)
            if paper is not None:
                return paper, False, None
        if relationship in _RELATED_RELATIONSHIPS:
            if related_paper_id is None:
                raise ValueError(
                    f"{relationship.value} persistence requires related_paper_id"
                )
            self._require_paper(related_paper_id)
            return self._new_paper(resolution_result), True, related_paper_id
        if relationship == IdentityRelationship.EXACT_FILE_DUPLICATE:
            raise ValueError("an exact file duplicate should have reused its Document")
        return self._new_paper(resolution_result), True, None

    def _existing_paper(
        self, paper_id: uuid.UUID | None, resolution_result: ResolutionResult
    ) -> Paper | None:
        if paper_id is not None:
            return self._require_paper(paper_id)
        return PaperRepository.get_by_doi(
            self.session, resolution_result.metadata.doi.value
        )

    def _new_paper(self, resolution_result: ResolutionResult) -> Paper:
        return PaperRepository.create(
            self.session, **canonical_paper_values(resolution_result)
        )

    def _require_paper(self, paper_id: uuid.UUID) -> Paper:
        paper = PaperRepository.get_by_id(self.session, paper_id)
        if paper is None:
            raise ValueError(f"paper does not exist: {paper_id}")
        return paper

    def _populate_new_paper(
        self, paper: Paper, resolution_result: ResolutionResult
    ) -> None:
        paper.metadata_evidence_json = [resolution_to_json(resolution_result)]
        paper.metadata_conflicts_json = list(resolution_result.conflicts)

    def _persist_authors(
        self, paper: Paper, resolution_result: ResolutionResult
    ) -> None:
        if paper.authors:
            return
        for position, values in enumerate(
            canonical_authors(resolution_result), start=1
        ):
            author = AuthorRepository.create(
                self.session,
                display_name=values["display_name"],
                given_name=values["given_name"],
                family_name=values["family_name"],
                normalized_name=values["normalized_name"],
            )
            AuthorRepository.attach(
                self.session,
                paper_id=paper.id,
                author_id=author.id,
                author_position=position,
                is_corresponding=None,
                provenance_json=values["provenance_json"],
            )


def persist_paper_result(
    session: Session,
    *,
    processing_result: PaperProcessingResult,
    resolution_result: ResolutionResult,
    identity_decision: IdentityDecision | None = None,
    existing_paper_id: uuid.UUID | None = None,
    related_paper_id: uuid.UUID | None = None,
    document_role: DocumentRole = DocumentRole.UNKNOWN,
    source_type: str = "local",
    source_identifier: str | None = None,
    source_uri: str | None = None,
) -> PersistenceResult:
    """Functional facade for the storage service."""

    return PaperStorageService(session).persist_paper_result(
        processing_result=processing_result,
        resolution_result=resolution_result,
        identity_decision=identity_decision,
        existing_paper_id=existing_paper_id,
        related_paper_id=related_paper_id,
        document_role=document_role,
        source_type=source_type,
        source_identifier=source_identifier,
        source_uri=source_uri,
    )


_RELATED_RELATIONSHIPS = {
    IdentityRelationship.RELATED_VERSION,
    IdentityRelationship.RELATED_CORRECTION,
    IdentityRelationship.RELATED_RETRACTION,
    IdentityRelationship.RELATED_SUPPLEMENT,
}


def _relation_type(relationship: IdentityRelationship) -> PaperRelationType:
    return {
        IdentityRelationship.RELATED_VERSION: PaperRelationType.VERSION_OF,
        IdentityRelationship.RELATED_CORRECTION: PaperRelationType.CORRECTION_OF,
        IdentityRelationship.RELATED_RETRACTION: PaperRelationType.RETRACTION_OF,
        IdentityRelationship.RELATED_SUPPLEMENT: PaperRelationType.SUPPLEMENT_OF,
    }[relationship]


def _action_for(
    identity_decision: IdentityDecision | None,
    paper_created: bool,
    document_created: bool,
    relation: Any,
) -> str:
    if relation is not None:
        return "created_paper_and_relation"
    if (
        identity_decision is not None
        and identity_decision.relationship == IdentityRelationship.SAME_PAPER
    ):
        return "attached_document_to_existing_paper"
    if paper_created and document_created:
        return "created_paper_and_document"
    return "attached_document"


def _processed_at(result: PaperProcessingResult) -> Any:
    from paper_knowledge_base.storage.models import utc_now

    return utc_now() if result.status.value else None
