"""Conservative deterministic comparison of paper documents and scholarly works."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from paper_knowledge_base.identity.models import (
    DocumentIdentity,
    IdentityConfidence,
    IdentityDecision,
    IdentityEvidence,
    IdentityMatch,
    IdentityMetadata,
    IdentityRelationship,
    IdentitySignal,
    IdentityThresholds,
    PublicationType,
)
from paper_knowledge_base.metadata.normalization import (
    author_overlap,
    normalize_doi,
    normalize_title,
    title_similarity,
)

if TYPE_CHECKING:
    from paper_knowledge_base.metadata.models import CanonicalPaperMetadata
    from paper_knowledge_base.processing.models import FileInfo, PaperProcessingResult


_DOI_IDENTIFIER_KEYS = {"doi", "crossref_doi"}
_EXTERNAL_ID_KEYS = {"openalex", "openalex_id", "pmid", "pmcid"}
_GENERIC_TITLE_WORDS = {
    "a",
    "an",
    "and",
    "article",
    "case",
    "for",
    "in",
    "introduction",
    "of",
    "on",
    "study",
    "the",
    "to",
}
_PREFIX_MARKERS = (
    (
        IdentityRelationship.RELATED_RETRACTION,
        IdentitySignal.RETRACTION_MARKER,
        (
            "retraction notice",
            "retraction note",
            "retracted article",
            "retraction",
        ),
    ),
    (
        IdentityRelationship.RELATED_CORRECTION,
        IdentitySignal.CORRECTION_MARKER,
        (
            "correction",
            "corrigendum",
            "erratum",
        ),
    ),
    (
        IdentityRelationship.RELATED_SUPPLEMENT,
        IdentitySignal.SUPPLEMENT_MARKER,
        (
            "supplementary material",
            "supplemental material",
            "supporting information",
            "supplement",
        ),
    ),
)
_WORK_TYPE_ALIASES = {
    "preprint": PublicationType.PREPRINT,
    "posted-content": PublicationType.PREPRINT,
    "posted content": PublicationType.PREPRINT,
    "accepted-manuscript": PublicationType.ACCEPTED_MANUSCRIPT,
    "accepted manuscript": PublicationType.ACCEPTED_MANUSCRIPT,
    "version of record": PublicationType.PUBLISHED_ARTICLE,
    "journal-article": PublicationType.PUBLISHED_ARTICLE,
    "article": PublicationType.PUBLISHED_ARTICLE,
    "published article": PublicationType.PUBLISHED_ARTICLE,
    "proceedings-article": PublicationType.CONFERENCE_PAPER,
    "conference-paper": PublicationType.CONFERENCE_PAPER,
    "supplement": PublicationType.SUPPLEMENT,
    "correction": PublicationType.CORRECTION,
    "erratum": PublicationType.CORRECTION,
    "corrigendum": PublicationType.CORRECTION,
    "retraction": PublicationType.RETRACTION_NOTICE,
    "retraction notice": PublicationType.RETRACTION_NOTICE,
}
_VERSION_PAIRS = {
    frozenset((PublicationType.PREPRINT, PublicationType.PUBLISHED_ARTICLE)),
    frozenset((PublicationType.ACCEPTED_MANUSCRIPT, PublicationType.PUBLISHED_ARTICLE)),
    frozenset((PublicationType.PREPRINT, PublicationType.CONFERENCE_PAPER)),
    frozenset((PublicationType.ACCEPTED_MANUSCRIPT, PublicationType.CONFERENCE_PAPER)),
}
DEFAULT_IDENTITY_THRESHOLDS = IdentityThresholds()


def document_from_processing_result(
    result: PaperProcessingResult,
    *,
    publication_type: PublicationType | str = PublicationType.UNKNOWN,
    provenance: Iterable[str] = (),
) -> DocumentIdentity:
    """Adapt the existing processing result without changing its model."""

    scholarly = result.scholarly
    metadata = IdentityMetadata(
        title=scholarly.title.value,
        authors=tuple(author.name for author in scholarly.authors),
        doi=scholarly.doi.value,
        publication_type=publication_type,
        provenance=tuple(provenance),
    )
    return DocumentIdentity(
        sha256=result.file.sha256,
        filename=result.file.filename,
        metadata=metadata,
    )


def document_from_canonical_metadata(
    file_info: FileInfo,
    metadata: CanonicalPaperMetadata,
    *,
    publication_type: PublicationType | str = PublicationType.UNKNOWN,
) -> DocumentIdentity:
    """Adapt canonical metadata and the existing file fingerprint to this domain."""

    provenance = {
        item.source
        for value in (metadata.title, metadata.doi, metadata.year, metadata.venue)
        for item in value.provenance
    }
    return DocumentIdentity(
        sha256=file_info.sha256,
        filename=file_info.filename,
        metadata=IdentityMetadata(
            title=_string_value(metadata.title.value),
            authors=tuple(author.display_name for author in metadata.authors),
            doi=_string_value(metadata.doi.value),
            year=_int_value(metadata.year.value),
            venue=metadata.venue.name,
            publication_type=publication_type,
            identifiers=dict(metadata.identifiers),
            provenance=tuple(sorted(provenance)),
        ),
    )


def compare_identity(
    document_a: DocumentIdentity,
    document_b: DocumentIdentity,
    *,
    thresholds: IdentityThresholds = DEFAULT_IDENTITY_THRESHOLDS,
) -> IdentityDecision:
    """Compare two documents and retain the source provenance supplied with them."""

    decision = _compare_identity(document_a, document_b, thresholds=thresholds)
    provenance = tuple(
        dict.fromkeys(document_a.metadata.provenance + document_b.metadata.provenance)
    )
    return replace(decision, provenance=provenance)


def _compare_identity(
    document_a: DocumentIdentity,
    document_b: DocumentIdentity,
    *,
    thresholds: IdentityThresholds = DEFAULT_IDENTITY_THRESHOLDS,
) -> IdentityDecision:
    """Compare two documents, short-circuiting deterministic identity first."""

    metadata_a = document_a.metadata
    metadata_b = document_b.metadata
    evidence: list[IdentityEvidence] = []
    conflicts: list[str] = []
    reasons: list[str] = []

    if document_a.sha256 and document_a.sha256 == document_b.sha256:
        return IdentityDecision(
            relationship=IdentityRelationship.EXACT_FILE_DUPLICATE,
            confidence=IdentityConfidence.HIGH,
            evidence=(
                IdentityEvidence(
                    IdentitySignal.SHA256_MATCH,
                    "Both documents have the same SHA-256 file fingerprint.",
                    True,
                ),
            ),
            reasons=("The binary PDF documents are identical.",),
            score=1.0,
            doi_match=bool(
                normalize_doi(metadata_a.doi)
                and normalize_doi(metadata_a.doi) == normalize_doi(metadata_b.doi)
            ),
        )

    evidence.append(
        IdentityEvidence(
            IdentitySignal.SHA256_DIFFERENT,
            "The PDF fingerprints differ; binary identity is not sufficient.",
            False,
            positive=False,
        )
    )
    title_score = title_similarity(metadata_a.title, metadata_b.title)
    authors_score, first_author_match = _author_similarity(
        metadata_a.authors, metadata_b.authors
    )
    year_match, year_adjacent = _year_evidence(
        metadata_a.year, metadata_b.year, thresholds.maximum_version_year_gap
    )
    doi_a = normalize_doi(metadata_a.doi) or _identifier_doi(metadata_a)
    doi_b = normalize_doi(metadata_b.doi) or _identifier_doi(metadata_b)
    doi_match = bool(doi_a and doi_b and doi_a == doi_b)
    doi_different = bool(doi_a and doi_b and doi_a != doi_b)

    _append_comparison_evidence(
        evidence,
        metadata_a,
        metadata_b,
        title_score,
        authors_score,
        first_author_match,
        year_match,
        year_adjacent,
        doi_match,
        doi_different,
        thresholds,
    )

    material = _related_material_decision(
        metadata_a,
        metadata_b,
        title_score,
        authors_score,
        first_author_match,
        thresholds,
        evidence,
    )
    if material is not None:
        return _finish(
            material, evidence, title_score, authors_score, doi_match, year_match
        )

    if doi_match:
        reasons.append("Normalized scholarly DOI values match.")
        return _decision(
            IdentityRelationship.SAME_PAPER,
            IdentityConfidence.HIGH,
            evidence,
            reasons,
            title_score,
            authors_score,
            doi_match,
            year_match,
            score=1.0,
        )

    external_id = _matching_external_identifier(metadata_a, metadata_b)
    if external_id:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.EXTERNAL_IDENTIFIER_MATCH,
                f"External scholarly identifier {external_id!r} matches.",
                True,
            )
        )
        reasons.append("A non-DOI scholarly work identifier matches.")
        return _decision(
            IdentityRelationship.SAME_PAPER,
            IdentityConfidence.HIGH,
            evidence,
            reasons,
            title_score,
            authors_score,
            doi_match,
            year_match,
            score=0.98,
        )

    version = _version_decision(
        metadata_a,
        metadata_b,
        title_score,
        authors_score,
        first_author_match,
        year_match,
        year_adjacent,
        thresholds,
        evidence,
    )
    if version is not None:
        return _finish(
            version, evidence, title_score, authors_score, doi_match, year_match
        )

    if _doi_conflict_is_distinct(
        doi_different, title_score, authors_score, metadata_a, metadata_b
    ):
        conflicts.append(
            "Both documents have different DOIs and incompatible metadata."
        )
        return _decision(
            IdentityRelationship.DISTINCT,
            IdentityConfidence.HIGH,
            evidence,
            (
                "Different identifiers and disjoint scholarly metadata indicate different works.",
            ),
            title_score,
            authors_score,
            doi_match,
            year_match,
            conflicts=conflicts,
            score=0.0,
        )

    if _same_paper_without_doi(
        metadata_a,
        metadata_b,
        title_score,
        authors_score,
        first_author_match,
        year_match,
        year_adjacent,
        thresholds,
    ):
        confidence = (
            IdentityConfidence.HIGH
            if normalize_title(metadata_a.title) == normalize_title(metadata_b.title)
            and year_match
            else IdentityConfidence.MEDIUM
        )
        return _decision(
            IdentityRelationship.SAME_PAPER,
            confidence,
            evidence,
            (
                "Title, author, and publication-date evidence support the same scholarly work.",
            ),
            title_score,
            authors_score,
            doi_match,
            year_match,
            score=_similarity_score(
                title_score, authors_score, year_match, year_adjacent
            ),
        )

    if _strong_title_author_contradiction(
        metadata_a, metadata_b, title_score, authors_score
    ):
        if _generic_title(metadata_a.title) or _generic_title(metadata_b.title):
            reasons.append(
                "A generic title with weak author evidence is not safe to merge."
            )
            relationship = IdentityRelationship.AMBIGUOUS
            confidence = IdentityConfidence.LOW
        else:
            reasons.append("The titles are the same but the author lists are disjoint.")
            relationship = IdentityRelationship.DISTINCT
            confidence = IdentityConfidence.MEDIUM
        return _decision(
            relationship,
            confidence,
            evidence,
            reasons,
            title_score,
            authors_score,
            doi_match,
            year_match,
            score=_similarity_score(
                title_score, authors_score, year_match, year_adjacent
            ),
        )

    evidence.append(
        IdentityEvidence(
            IdentitySignal.INSUFFICIENT_EVIDENCE,
            "Available metadata does not meet an automatic identity threshold.",
            None,
            positive=False,
        )
    )
    return _decision(
        IdentityRelationship.AMBIGUOUS,
        IdentityConfidence.LOW,
        evidence,
        ("The evidence is insufficient for a safe automatic merge.",),
        title_score,
        authors_score,
        doi_match,
        year_match,
        score=_similarity_score(title_score, authors_score, year_match, year_adjacent),
    )


def find_identity_matches(
    incoming: DocumentIdentity,
    existing_candidates: Iterable[DocumentIdentity],
    *,
    thresholds: IdentityThresholds = DEFAULT_IDENTITY_THRESHOLDS,
    limit: int | None = None,
) -> tuple[IdentityMatch, ...]:
    """Rank pairwise decisions without introducing a database or index."""

    matches = [
        IdentityMatch(
            candidate, compare_identity(incoming, candidate, thresholds=thresholds)
        )
        for candidate in existing_candidates
    ]
    matches.sort(key=_match_sort_key, reverse=True)
    return tuple(matches[:limit] if limit is not None else matches)


def _append_comparison_evidence(
    evidence: list[IdentityEvidence],
    left: IdentityMetadata,
    right: IdentityMetadata,
    title_score: float,
    author_score: float,
    first_author_match: bool,
    year_match: bool | None,
    year_adjacent: bool,
    doi_match: bool,
    doi_different: bool,
    thresholds: IdentityThresholds,
) -> None:
    if doi_match:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.DOI_MATCH, "Normalized DOI values match.", True
            )
        )
    elif doi_different:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.DOI_DIFFERENT,
                "Both documents have DOI values, but they are different.",
                False,
                positive=False,
            )
        )
    if normalize_title(left.title) == normalize_title(right.title) and normalize_title(
        left.title
    ):
        evidence.append(
            IdentityEvidence(
                IdentitySignal.TITLE_EXACT, "Normalized titles match exactly.", 1.0
            )
        )
    elif title_score >= thresholds.likely_title_similarity:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.TITLE_SIMILAR,
                "Titles are highly similar after normalization.",
                round(title_score, 3),
            )
        )
    else:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.TITLE_MISMATCH,
                "Titles are not sufficiently similar.",
                round(title_score, 3),
                positive=False,
            )
        )
    if author_score >= thresholds.strong_author_similarity:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.AUTHORS_STRONG_OVERLAP,
                "Author lists overlap strongly.",
                round(author_score, 3),
            )
        )
    elif author_score >= thresholds.partial_author_similarity:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.AUTHORS_PARTIAL_OVERLAP,
                "Author lists have partial overlap.",
                round(author_score, 3),
            )
        )
    elif left.authors and right.authors:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.AUTHORS_DISJOINT,
                "Author lists do not overlap conservatively.",
                round(author_score, 3),
                positive=False,
            )
        )
    if first_author_match:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.FIRST_AUTHOR_MATCH,
                "First-author identity matches conservatively.",
                True,
            )
        )
    if year_match:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.YEAR_MATCH, "Publication years match.", True
            )
        )
    elif year_adjacent:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.YEAR_ADJACENT,
                "Publication years are adjacent and compatible with a version relationship.",
                True,
            )
        )
    elif left.year is not None and right.year is not None:
        evidence.append(
            IdentityEvidence(
                IdentitySignal.YEAR_INCOMPATIBLE,
                "Publication years differ materially.",
                False,
                positive=False,
            )
        )
    if _venue_match(left.venue, right.venue):
        evidence.append(
            IdentityEvidence(
                IdentitySignal.VENUE_MATCH, "Normalized venues match.", True
            )
        )


def _related_material_decision(
    left: IdentityMetadata,
    right: IdentityMetadata,
    title_score: float,
    authors_score: float,
    first_author_match: bool,
    thresholds: IdentityThresholds,
    evidence: list[IdentityEvidence],
) -> IdentityDecision | None:
    left_relation, left_signal = _material_marker(left)
    right_relation, right_signal = _material_marker(right)
    relation = left_relation or right_relation
    signal = left_signal or right_signal
    if relation is None or signal is None:
        return None
    if title_score < thresholds.minimum_related_material_title_similarity:
        return None
    if not (
        authors_score >= thresholds.partial_author_similarity or first_author_match
    ):
        return None
    evidence.append(
        IdentityEvidence(
            signal, "One document is explicitly marked as related material.", True
        )
    )
    label = {
        IdentityRelationship.RELATED_CORRECTION: "correction/erratum/corrigendum",
        IdentityRelationship.RELATED_RETRACTION: "retraction notice",
        IdentityRelationship.RELATED_SUPPLEMENT: "supplementary material",
    }[relation]
    return _decision(
        relation,
        IdentityConfidence.HIGH
        if title_score >= thresholds.high_title_similarity
        else IdentityConfidence.MEDIUM,
        evidence,
        (
            f"The marked {label} is related to the other document but is not the same scholarly work.",
        ),
        title_score,
        authors_score,
        None,
        None,
        score=0.7 * title_score + 0.3 * authors_score,
    )


def _version_decision(
    left: IdentityMetadata,
    right: IdentityMetadata,
    title_score: float,
    authors_score: float,
    first_author_match: bool,
    year_match: bool | None,
    year_adjacent: bool,
    thresholds: IdentityThresholds,
    evidence: list[IdentityEvidence],
) -> IdentityDecision | None:
    left_type = _publication_type(left)
    right_type = _publication_type(right)
    pair = frozenset((left_type, right_type))
    if pair not in _VERSION_PAIRS:
        return None
    compatible_year = (
        year_match is True or year_adjacent or left.year is None or right.year is None
    )
    strong_authors = (
        authors_score >= thresholds.partial_author_similarity or first_author_match
    )
    if (
        title_score < thresholds.minimum_version_title_similarity
        or not strong_authors
        or not compatible_year
    ):
        return None
    if left_type == PublicationType.PREPRINT or right_type == PublicationType.PREPRINT:
        signal = IdentitySignal.PREPRINT_PUBLISHED_PAIR
        detail = "Preprint and published/conference publication types strongly match by metadata."
    else:
        signal = IdentitySignal.MANUSCRIPT_PUBLISHED_PAIR
        detail = "Accepted-manuscript and published/conference publication types strongly match by metadata."
    evidence.append(IdentityEvidence(signal, detail, True))
    return _decision(
        IdentityRelationship.RELATED_VERSION,
        IdentityConfidence.HIGH
        if title_score >= thresholds.high_title_similarity
        and authors_score >= thresholds.strong_author_similarity
        else IdentityConfidence.MEDIUM,
        evidence,
        (
            "The documents represent closely related publication versions; storage should preserve both.",
        ),
        title_score,
        authors_score,
        None,
        year_match,
        score=0.55 * title_score + 0.4 * authors_score + (0.05 if year_match else 0.0),
    )


def _same_paper_without_doi(
    left: IdentityMetadata,
    right: IdentityMetadata,
    title_score: float,
    authors_score: float,
    first_author_match: bool,
    year_match: bool | None,
    year_adjacent: bool,
    thresholds: IdentityThresholds,
) -> bool:
    title_exact = bool(
        normalize_title(left.title)
        and normalize_title(left.title) == normalize_title(right.title)
    )
    authors_strong = authors_score >= thresholds.strong_author_similarity
    authors_adequate = (
        authors_score >= thresholds.partial_author_similarity and first_author_match
    )
    years_compatible = (
        year_match is True or year_adjacent or left.year is None or right.year is None
    )
    if not years_compatible:
        return False
    if title_exact and authors_strong:
        return True
    return title_score >= thresholds.minimum_same_paper_title_similarity and (
        authors_strong or authors_adequate
    )


def _strong_title_author_contradiction(
    left: IdentityMetadata,
    right: IdentityMetadata,
    title_score: float,
    authors_score: float,
) -> bool:
    return bool(
        normalize_title(left.title)
        and normalize_title(left.title) == normalize_title(right.title)
        and authors_score == 0.0
        and title_score >= 0.99
    )


def _doi_conflict_is_distinct(
    doi_different: bool,
    title_score: float,
    authors_score: float,
    left: IdentityMetadata,
    right: IdentityMetadata,
) -> bool:
    return bool(
        doi_different
        and title_score < 0.70
        and authors_score < 0.25
        and left.authors
        and right.authors
    )


def _author_similarity(left: Sequence[str], right: Sequence[str]) -> tuple[float, bool]:
    if not left or not right:
        return 0.0, False
    forward = author_overlap(left, right)
    backward = author_overlap(right, left)
    return min(forward, backward), bool(author_overlap(left[:1], right[:1]))


def _year_evidence(
    left: int | None, right: int | None, maximum_version_year_gap: int
) -> tuple[bool | None, bool]:
    if left is None or right is None:
        return None, False
    gap = abs(left - right)
    return left == right, 0 < gap <= maximum_version_year_gap


def _publication_type(metadata: IdentityMetadata) -> PublicationType:
    if isinstance(metadata.publication_type, PublicationType):
        return metadata.publication_type
    normalized = str(metadata.publication_type).strip().casefold().replace("_", " ")
    return _WORK_TYPE_ALIASES.get(normalized, PublicationType.UNKNOWN)


def _material_marker(
    metadata: IdentityMetadata,
) -> tuple[IdentityRelationship | None, IdentitySignal | None]:
    kind = _publication_type(metadata)
    if kind == PublicationType.CORRECTION:
        return IdentityRelationship.RELATED_CORRECTION, IdentitySignal.CORRECTION_MARKER
    if kind == PublicationType.RETRACTION_NOTICE:
        return IdentityRelationship.RELATED_RETRACTION, IdentitySignal.RETRACTION_MARKER
    if kind == PublicationType.SUPPLEMENT:
        return IdentityRelationship.RELATED_SUPPLEMENT, IdentitySignal.SUPPLEMENT_MARKER
    title = normalize_title(metadata.title)
    for relation, signal, markers in _PREFIX_MARKERS:
        if any(title.startswith(marker) for marker in markers):
            return relation, signal
    return None, None


def _base_title(metadata: IdentityMetadata) -> str:
    title = normalize_title(metadata.title)
    for _, _, markers in _PREFIX_MARKERS:
        for marker in markers:
            if title.startswith((marker + ":", marker + " to ")):
                return title[len(marker) :].lstrip(" :")
    return title


def _venue_match(left: str | None, right: str | None) -> bool:
    return bool(left and right and normalize_title(left) == normalize_title(right))


def _generic_title(title: str | None) -> bool:
    tokens = set(normalize_title(title).split())
    return len(tokens) <= 4 and bool(tokens) and tokens <= _GENERIC_TITLE_WORDS


def _identifier_doi(metadata: IdentityMetadata) -> str | None:
    for key, value in metadata.identifiers.items():
        if key.casefold() in _DOI_IDENTIFIER_KEYS:
            return normalize_doi(value)
    return None


def _matching_external_identifier(
    left: IdentityMetadata, right: IdentityMetadata
) -> str | None:
    for key, value in left.identifiers.items():
        if key.casefold() not in _EXTERNAL_ID_KEYS:
            continue
        if value and value == right.identifiers.get(key):
            return key
    return None


def _similarity_score(
    title_score: float,
    authors_score: float,
    year_match: bool | None,
    year_adjacent: bool,
) -> float:
    return round(
        0.55 * title_score
        + 0.4 * authors_score
        + (0.05 if year_match else 0.025 if year_adjacent else 0.0),
        3,
    )


def _match_sort_key(match: IdentityMatch) -> tuple[int, int, float]:
    relationship_rank = {
        IdentityRelationship.EXACT_FILE_DUPLICATE: 8,
        IdentityRelationship.SAME_PAPER: 7,
        IdentityRelationship.RELATED_VERSION: 6,
        IdentityRelationship.RELATED_CORRECTION: 5,
        IdentityRelationship.RELATED_RETRACTION: 5,
        IdentityRelationship.RELATED_SUPPLEMENT: 5,
        IdentityRelationship.AMBIGUOUS: 2,
        IdentityRelationship.DISTINCT: 1,
    }
    confidence_rank = {
        IdentityConfidence.HIGH: 3,
        IdentityConfidence.MEDIUM: 2,
        IdentityConfidence.LOW: 1,
    }
    decision = match.decision
    return (
        relationship_rank[decision.relationship],
        confidence_rank[decision.confidence],
        decision.score or 0.0,
    )


def _finish(
    decision: IdentityDecision,
    evidence: list[IdentityEvidence],
    title_score: float,
    authors_score: float,
    doi_match: bool,
    year_match: bool | None,
) -> IdentityDecision:
    return replace(
        decision,
        evidence=tuple(evidence),
        title_similarity=title_score,
        author_similarity=authors_score,
        doi_match=doi_match,
        year_match=year_match,
    )


def _decision(
    relationship: IdentityRelationship,
    confidence: IdentityConfidence,
    evidence: Sequence[IdentityEvidence],
    reasons: Sequence[str],
    title_score: float,
    authors_score: float,
    doi_match: bool | None,
    year_match: bool | None,
    *,
    conflicts: Sequence[str] = (),
    score: float | None = None,
) -> IdentityDecision:
    return IdentityDecision(
        relationship=relationship,
        confidence=confidence,
        evidence=tuple(evidence),
        conflicts=tuple(conflicts),
        reasons=tuple(reasons),
        score=score,
        title_similarity=round(title_score, 3),
        author_similarity=round(authors_score, 3),
        doi_match=doi_match,
        year_match=year_match,
    )


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_value(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
