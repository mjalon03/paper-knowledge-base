"""Parser- and storage-independent models for paper identity decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class IdentityRelationship(str, Enum):
    """The relationship between two concrete documents."""

    EXACT_FILE_DUPLICATE = "exact_file_duplicate"
    SAME_PAPER = "same_paper"
    RELATED_VERSION = "related_version"
    RELATED_SUPPLEMENT = "related_supplement"
    RELATED_CORRECTION = "related_correction"
    RELATED_RETRACTION = "related_retraction"
    DISTINCT = "distinct"
    AMBIGUOUS = "ambiguous"


class IdentityConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PublicationType(str, Enum):
    UNKNOWN = "unknown"
    PREPRINT = "preprint"
    ACCEPTED_MANUSCRIPT = "accepted_manuscript"
    PUBLISHED_ARTICLE = "published_article"
    CONFERENCE_PAPER = "conference_paper"
    SUPPLEMENT = "supplement"
    CORRECTION = "correction"
    RETRACTION_NOTICE = "retraction_notice"


class IdentitySignal(str, Enum):
    """Machine-readable evidence exposed in an identity decision."""

    SHA256_MATCH = "sha256_match"
    SHA256_DIFFERENT = "sha256_different"
    DOI_MATCH = "doi_match"
    DOI_DIFFERENT = "doi_different"
    EXTERNAL_IDENTIFIER_MATCH = "external_identifier_match"
    TITLE_EXACT = "title_exact"
    TITLE_SIMILAR = "title_similar"
    TITLE_MISMATCH = "title_mismatch"
    AUTHORS_STRONG_OVERLAP = "authors_strong_overlap"
    AUTHORS_PARTIAL_OVERLAP = "authors_partial_overlap"
    AUTHORS_DISJOINT = "authors_disjoint"
    FIRST_AUTHOR_MATCH = "first_author_match"
    YEAR_MATCH = "year_match"
    YEAR_ADJACENT = "year_adjacent"
    YEAR_INCOMPATIBLE = "year_incompatible"
    VENUE_MATCH = "venue_match"
    PREPRINT_PUBLISHED_PAIR = "preprint_published_pair"
    MANUSCRIPT_PUBLISHED_PAIR = "manuscript_published_pair"
    SUPPLEMENT_MARKER = "supplement_marker"
    CORRECTION_MARKER = "correction_marker"
    RETRACTION_MARKER = "retraction_marker"
    FILENAME_ONLY = "filename_only"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class IdentityMetadata:
    """Comparable scholarly metadata, intentionally separate from a PDF file."""

    title: str | None = None
    authors: tuple[str, ...] = ()
    doi: str | None = None
    year: int | None = None
    venue: str | None = None
    publication_type: PublicationType | str = PublicationType.UNKNOWN
    identifiers: Mapping[str, str] = field(default_factory=dict)
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentIdentity:
    """A concrete document plus the scholarly metadata used to compare it."""

    sha256: str | None
    metadata: IdentityMetadata
    filename: str | None = None


@dataclass(frozen=True)
class IdentityEvidence:
    """One inspectable signal; ``value`` is a score or boolean when applicable."""

    signal: IdentitySignal
    detail: str
    value: float | bool | None = None
    positive: bool = True


@dataclass(frozen=True)
class IdentityDecision:
    """Explainable identity output for future persistence or manual review."""

    relationship: IdentityRelationship
    confidence: IdentityConfidence
    evidence: tuple[IdentityEvidence, ...] = ()
    conflicts: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    score: float | None = None
    title_similarity: float = 0.0
    author_similarity: float = 0.0
    doi_match: bool | None = None
    year_match: bool | None = None

    @property
    def signals(self) -> tuple[IdentityEvidence, ...]:
        """Compatibility alias for callers that call evidence signals."""

        return self.evidence


@dataclass(frozen=True)
class IdentityThresholds:
    """Centralized, deliberately conservative deterministic thresholds."""

    high_title_similarity: float = 0.92
    likely_title_similarity: float = 0.86
    minimum_same_paper_title_similarity: float = 0.75
    strong_author_similarity: float = 0.75
    partial_author_similarity: float = 0.50
    maximum_version_year_gap: int = 2
    minimum_version_title_similarity: float = 0.86
    minimum_related_material_title_similarity: float = 0.68


@dataclass(frozen=True)
class IdentityMatch:
    """A ranked pairwise decision returned by collection matching."""

    candidate: DocumentIdentity
    decision: IdentityDecision
