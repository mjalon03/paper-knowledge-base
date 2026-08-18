from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from alembic import command
from paper_knowledge_base.identity import (
    IdentityConfidence,
    IdentityDecision,
    IdentityEvidence,
    IdentityRelationship,
    IdentitySignal,
)
from paper_knowledge_base.metadata.models import (
    CandidateMetadata,
    CanonicalAuthor,
    CanonicalPaperMetadata,
    CanonicalValue,
    CanonicalVenue,
    Confidence,
    MetadataEvidence,
    MetadataProvenance,
    ResolutionResult,
    ResolutionStatus,
)
from paper_knowledge_base.processing.models import (
    Author as ProcessingAuthor,
)
from paper_knowledge_base.processing.models import (
    DocumentContent,
    FileInfo,
    MetadataField,
    PaperProcessingResult,
    PDFInspection,
    ProcessingRoute,
    ProcessingStatus,
    ScholarlyMetadata,
)
from paper_knowledge_base.storage.database import (
    create_database_engine,
    create_schema_for_tests,
    create_session_factory,
    session_scope,
)
from paper_knowledge_base.storage.models import (
    Author,
    DocumentRole,
    Paper,
    PaperAuthor,
    PaperDocument,
    PaperRelation,
    PaperRelationType,
)
from paper_knowledge_base.storage.repositories import (
    AuthorRepository,
    DocumentRepository,
    PaperDocumentRepository,
    PaperRelationRepository,
    PaperRepository,
)
from paper_knowledge_base.storage.service import persist_paper_result


@pytest.fixture
def session_factory():
    engine = create_database_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_schema_for_tests(engine)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


def test_create_paper_document_and_timestamps(session_factory) -> None:
    with session_scope(session_factory) as session:
        paper = PaperRepository.create(
            session,
            canonical_title="A paper",
            normalized_title="a paper",
            doi="10.1234/example",
            metadata_provenance_json={},
            metadata_evidence_json=[],
            metadata_conflicts_json=[],
        )
        document, created = DocumentRepository.get_or_create_by_sha256(
            session,
            sha256="a" * 64,
            filename="paper.pdf",
            source_type="local",
        )

    assert created is True
    assert paper.id is not None
    assert paper.created_at.tzinfo is not None
    assert document.processed_at is None


def test_sha256_is_unique_and_get_by_sha_reuses_document(session_factory) -> None:
    with session_scope(session_factory) as session:
        first, created = DocumentRepository.get_or_create_by_sha256(
            session, sha256="b" * 64, filename="one.pdf"
        )
        second, reused = DocumentRepository.get_or_create_by_sha256(
            session, sha256="b" * 64, filename="renamed.pdf"
        )

    assert created is True
    assert reused is False
    assert second.id == first.id
    assert second.filename == "one.pdf"


def test_doi_is_normalized_and_null_papers_are_allowed(session_factory) -> None:
    with session_scope(session_factory) as session:
        first = PaperRepository.create(
            session,
            canonical_title="First",
            normalized_title="first",
            doi="10.1234/abc",
            metadata_provenance_json={},
            metadata_evidence_json=[],
            metadata_conflicts_json=[],
        )
        assert (
            PaperRepository.get_by_doi(session, "https://doi.org/10.1234/ABC").id
            == first.id
        )
        PaperRepository.create(
            session,
            canonical_title="No DOI one",
            normalized_title="no doi one",
            doi=None,
            metadata_provenance_json={},
            metadata_evidence_json=[],
            metadata_conflicts_json=[],
        )
        PaperRepository.create(
            session,
            canonical_title="No DOI two",
            normalized_title="no doi two",
            doi=None,
            metadata_provenance_json={},
            metadata_evidence_json=[],
            metadata_conflicts_json=[],
        )

        with pytest.raises(IntegrityError):
            PaperRepository.create(
                session,
                canonical_title="Duplicate DOI",
                normalized_title="duplicate doi",
                doi="10.1234/ABC",
                metadata_provenance_json={},
                metadata_evidence_json=[],
                metadata_conflicts_json=[],
            )
        session.rollback()


def test_one_paper_supports_multiple_documents_and_duplicate_association_is_blocked(
    session_factory,
) -> None:
    with session_scope(session_factory) as session:
        paper = _create_paper(session, "10.1234/multi")
        first = DocumentRepository.create(session, sha256="c" * 64, filename="one.pdf")
        second = DocumentRepository.create(session, sha256="d" * 64, filename="two.pdf")
        PaperDocumentRepository.attach(
            session,
            paper_id=paper.id,
            document_id=first.id,
            role=DocumentRole.PUBLISHER_VERSION,
        )
        PaperDocumentRepository.attach(
            session,
            paper_id=paper.id,
            document_id=second.id,
            role=DocumentRole.REPOSITORY_COPY,
        )
        with pytest.raises(IntegrityError), session.begin_nested():
            PaperDocumentRepository.attach(
                session, paper_id=paper.id, document_id=first.id
            )
        assert (
            len(
                session.scalars(
                    select(PaperDocument).where(PaperDocument.paper_id == paper.id)
                ).all()
            )
            == 2
        )


def test_same_normalized_author_name_does_not_imply_same_person(
    session_factory,
) -> None:
    with session_scope(session_factory) as session:
        first = AuthorRepository.create(
            session,
            display_name="J. Smith",
            normalized_name="j smith",
        )
        second = AuthorRepository.create(
            session,
            display_name="J. Smith",
            normalized_name="j smith",
        )

    assert first.id != second.id


def test_author_order_is_preserved(session_factory) -> None:
    with session_scope(session_factory) as session:
        paper = _create_paper(session, "10.1234/authors")
        for position, name in enumerate(("First Author", "Second Author"), start=1):
            author = AuthorRepository.create(
                session, display_name=name, normalized_name=name.casefold()
            )
            AuthorRepository.attach(
                session,
                paper_id=paper.id,
                author_id=author.id,
                author_position=position,
                is_corresponding=None,
                provenance_json={"source": "crossref"},
            )
        ordered = (
            session.execute(
                select(Author.display_name)
                .join(PaperAuthor, PaperAuthor.author_id == Author.id)
                .where(PaperAuthor.paper_id == paper.id)
                .order_by(PaperAuthor.author_position)
            )
            .scalars()
            .all()
        )

    assert ordered == ["First Author", "Second Author"]


def test_paper_relations_and_duplicate_edges(session_factory) -> None:
    with session_scope(session_factory) as session:
        preprint = _create_paper(session, "10.1234/preprint")
        journal = _create_paper(session, "10.1234/journal")
        relation = PaperRelationRepository.create(
            session,
            source_paper_id=preprint.id,
            target_paper_id=journal.id,
            relation_type=PaperRelationType.VERSION_OF.value,
            confidence="high",
            evidence_json={"signal": "preprint_published_pair"},
        )
        with pytest.raises(IntegrityError):
            PaperRelationRepository.create(
                session,
                source_paper_id=preprint.id,
                target_paper_id=journal.id,
                relation_type=PaperRelationType.VERSION_OF.value,
                confidence="high",
                evidence_json={},
            )
        session.rollback()
        assert relation.relation_type == "version_of"


def test_transaction_scope_rolls_back_on_failure(session_factory) -> None:
    with pytest.raises(RuntimeError), session_scope(session_factory) as session:
        _create_paper(session, "10.1234/rollback")
        raise RuntimeError("force rollback")

    with session_scope(session_factory) as session:
        assert (
            session.scalar(select(Paper).where(Paper.doi == "10.1234/rollback")) is None
        )


def test_associations_restrict_accidental_paper_deletion(session_factory) -> None:
    with session_scope(session_factory) as session:
        paper = _create_paper(session, "10.1234/restrict")
        document = DocumentRepository.create(
            session, sha256="6" * 64, filename="protected.pdf"
        )
        PaperDocumentRepository.attach(
            session, paper_id=paper.id, document_id=document.id
        )
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(delete(Paper).where(Paper.id == paper.id))


def test_migration_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "storage.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")

    command.upgrade(config, "head")
    engine = create_database_engine(f"sqlite+pysqlite:///{database_path}")
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "authors",
        "documents",
        "paper_authors",
        "paper_documents",
        "paper_relations",
        "papers",
    }
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    assert "papers" in inspect(engine).get_table_names()
    engine.dispose()


def test_service_same_paper_reuses_paper_and_attaches_document(session_factory) -> None:
    processing = _processing("e" * 64, "Same Paper", "10.1234/same")
    resolution = _resolution("Same Paper", "10.1234/same", ("Ada Author",))
    with session_scope(session_factory) as session:
        first = persist_paper_result(
            session, processing_result=processing, resolution_result=resolution
        )
        second = persist_paper_result(
            session,
            processing_result=_processing("f" * 64, "Same Paper", "10.1234/same"),
            resolution_result=resolution,
            identity_decision=_decision(IdentityRelationship.SAME_PAPER),
            existing_paper_id=first.paper_id,
        )
        assert first.paper_id == second.paper_id
        assert first.document_id != second.document_id
        assert (
            session.scalar(select(Paper).where(Paper.doi == "10.1234/same")) is not None
        )
        assert len(session.scalars(select(Paper)).all()) == 1
        assert len(session.scalars(select(PaperDocument)).all()) == 2


def test_service_exact_rerun_reuses_document_and_paper(session_factory) -> None:
    processing = _processing("1" * 64, "Rerun", "10.1234/rerun")
    resolution = _resolution("Rerun", "10.1234/rerun", ("Ada Author",))
    with session_scope(session_factory) as session:
        first = persist_paper_result(
            session, processing_result=processing, resolution_result=resolution
        )
        second = persist_paper_result(
            session, processing_result=processing, resolution_result=resolution
        )
        assert second.action == "reused_document"
        assert second.document_id == first.document_id
        assert second.paper_id == first.paper_id
        assert len(session.scalars(select(Paper)).all()) == 1
        assert len(session.scalars(select(PaperDocument)).all()) == 1


def test_service_related_version_creates_two_papers_and_relation(
    session_factory,
) -> None:
    journal_processing = _processing("2" * 64, "Versioned Paper", "10.1234/journal")
    resolution = _resolution("Versioned Paper", "10.1234/journal", ("Ada Author",))
    preprint_processing = _processing("3" * 64, "Versioned Paper", "10.1234/preprint")
    with session_scope(session_factory) as session:
        journal = persist_paper_result(
            session,
            processing_result=journal_processing,
            resolution_result=resolution,
        )
        preprint = persist_paper_result(
            session,
            processing_result=preprint_processing,
            resolution_result=_resolution(
                "Versioned Paper", "10.1234/preprint", ("Ada Author",)
            ),
            identity_decision=_decision(IdentityRelationship.RELATED_VERSION),
            related_paper_id=journal.paper_id,
        )
        relation = session.get(PaperRelation, preprint.relation_id)
        assert relation is not None
        assert relation.source_paper_id == preprint.paper_id
        assert relation.target_paper_id == journal.paper_id
        assert relation.relation_type == PaperRelationType.VERSION_OF.value
        assert len(session.scalars(select(Paper)).all()) == 2


def test_service_ambiguous_creates_separate_paper(session_factory) -> None:
    resolution = _resolution("Ambiguous", None, ("Ada Author",))
    with session_scope(session_factory) as session:
        first = persist_paper_result(
            session,
            processing_result=_processing("4" * 64, "Ambiguous", None),
            resolution_result=resolution,
        )
        second = persist_paper_result(
            session,
            processing_result=_processing("5" * 64, "Ambiguous", None),
            resolution_result=resolution,
            identity_decision=_decision(IdentityRelationship.AMBIGUOUS),
        )
        assert first.paper_id != second.paper_id
        assert len(session.scalars(select(Paper)).all()) == 2


def _create_paper(session, doi: str | None) -> Paper:
    return PaperRepository.create(
        session,
        canonical_title="Fixture",
        normalized_title="fixture",
        doi=doi,
        metadata_provenance_json={},
        metadata_evidence_json=[],
        metadata_conflicts_json=[],
    )


def _processing(sha256: str, title: str, doi: str | None) -> PaperProcessingResult:
    return PaperProcessingResult(
        file=FileInfo(Path("paper.pdf"), "paper.pdf", 10, sha256),
        inspection=PDFInspection(1, 500, 1, 1.0, 500.0, True),
        route=ProcessingRoute.EMBEDDED_TEXT,
        status=ProcessingStatus.SUCCESS,
        scholarly=ScholarlyMetadata(
            title=MetadataField(title, "grobid"),
            doi=MetadataField(doi, "grobid" if doi else None),
            authors=(ProcessingAuthor("Ada Author", "grobid"),),
        ),
        document=DocumentContent(),
        parser_runs={},
    )


def _resolution(
    title: str, doi: str | None, authors: tuple[str, ...]
) -> ResolutionResult:
    provenance = (MetadataProvenance("crossref", "fixture"),)
    metadata = CanonicalPaperMetadata(
        title=CanonicalValue(title, Confidence.HIGH, provenance),
        doi=CanonicalValue(doi, Confidence.HIGH, provenance),
        authors=tuple(CanonicalAuthor(name, provenance=provenance) for name in authors),
        year=CanonicalValue(2024, Confidence.HIGH, provenance),
        venue=CanonicalVenue("Example Journal", provenance=provenance),
        identifiers={"crossref": "fixture"},
    )
    return ResolutionResult(
        status=ResolutionStatus.RESOLVED,
        metadata=metadata,
        candidate=CandidateMetadata(title, doi, authors, "grobid", "grobid"),
        evidence=(
            MetadataEvidence(
                source="crossref",
                source_id="fixture",
                matched_by="doi",
                title_similarity=1.0,
                author_overlap=1.0,
                doi_match=True,
                record=None,
            ),
        ),
    )


def _decision(relationship: IdentityRelationship) -> IdentityDecision:
    return IdentityDecision(
        relationship=relationship,
        confidence=IdentityConfidence.HIGH,
        evidence=(
            IdentityEvidence(IdentitySignal.TITLE_EXACT, "fixture evidence", True),
        ),
        reasons=("fixture",),
    )
