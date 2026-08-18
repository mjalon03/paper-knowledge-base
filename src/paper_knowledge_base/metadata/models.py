"""Parser-independent, provenance-aware metadata resolution domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNVERIFIED = "unverified"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class SourceAuthor:
    display_name: str
    given_name: str | None = None
    family_name: str | None = None


@dataclass(frozen=True)
class SourceRecord:
    source: str
    source_id: str
    doi: str | None
    title: str | None
    authors: tuple[SourceAuthor, ...] = ()
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    work_type: str | None = None
    identifiers: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class MetadataProvenance:
    source: str
    source_id: str | None = None


@dataclass(frozen=True)
class MetadataEvidence:
    source: str
    source_id: str | None
    matched_by: str
    title_similarity: float | None = None
    author_overlap: float | None = None
    doi_match: bool | None = None
    year_match: bool | None = None
    record: SourceRecord | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class CanonicalValue:
    value: str | int | None
    confidence: Confidence
    provenance: tuple[MetadataProvenance, ...] = ()


@dataclass(frozen=True)
class CanonicalAuthor:
    display_name: str
    given_name: str | None = None
    family_name: str | None = None
    provenance: tuple[MetadataProvenance, ...] = ()


@dataclass(frozen=True)
class CanonicalVenue:
    name: str | None
    publisher: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    provenance: tuple[MetadataProvenance, ...] = ()


@dataclass(frozen=True)
class CandidateMetadata:
    title: str | None
    doi: str | None
    authors: tuple[str, ...]
    title_source: str | None
    doi_source: str | None


@dataclass(frozen=True)
class CanonicalPaperMetadata:
    title: CanonicalValue
    doi: CanonicalValue
    authors: tuple[CanonicalAuthor, ...]
    year: CanonicalValue
    venue: CanonicalVenue
    identifiers: dict[str, str]


@dataclass(frozen=True)
class ResolutionResult:
    status: ResolutionStatus
    metadata: CanonicalPaperMetadata
    candidate: CandidateMetadata
    evidence: tuple[MetadataEvidence, ...]
    conflicts: tuple[str, ...] = ()
