"""Deterministic reconciliation of parser candidates with public source records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

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
    SourceRecord,
)
from paper_knowledge_base.metadata.normalization import (
    author_overlap,
    normalize_doi,
    title_similarity,
)
from paper_knowledge_base.metadata.sources.base import MetadataSourceError
from paper_knowledge_base.metadata.sources.crossref import CrossrefClient
from paper_knowledge_base.metadata.sources.openalex import OpenAlexClient
from paper_knowledge_base.processing.models import PaperProcessingResult

DOI_TITLE_COMPATIBILITY = 0.75
STRONG_SINGLE_SOURCE_SCORE = 0.90
STRONG_AGREED_SCORE = 0.80
AMBIGUITY_MARGIN = 0.05
JOURNAL_RECORD_BONUS = 0.10
JOURNAL_RECORD_TYPES = {"journal-article", "article"}


class MetadataSource(Protocol):
    source: str

    def lookup_doi(self, doi: str) -> SourceRecord | None: ...

    def search(
        self, title: str, *, year: int | None = None
    ) -> tuple[SourceRecord, ...]: ...


@dataclass(frozen=True)
class _ScoredRecord:
    record: SourceRecord
    score: float
    title_score: float
    author_score: float
    doi_match: bool


def resolve_metadata(
    processing_result: PaperProcessingResult,
    *,
    crossref: MetadataSource | None = None,
    openalex: MetadataSource | None = None,
) -> ResolutionResult:
    """Resolve normalized processing metadata without hiding parser candidates.

    DOI equality is strongest evidence, but a DOI response whose title is
    materially incompatible is returned as a conflict. Missing DOIs are only
    recovered from a strong deterministic title/author match, preferably with
    independent Crossref and OpenAlex agreement.
    """

    candidate = _candidate_from(processing_result)
    sources: tuple[MetadataSource, ...] = (
        crossref or CrossrefClient(),
        openalex or OpenAlexClient(),
    )
    records, evidence = _collect_records(candidate, sources)
    scored = tuple(_score(record, candidate) for record in records)
    return _resolve(candidate, scored, evidence)


def _candidate_from(result: PaperProcessingResult) -> CandidateMetadata:
    scholarly = result.scholarly
    return CandidateMetadata(
        title=scholarly.title.value,
        doi=normalize_doi(scholarly.doi.value),
        authors=tuple(author.name for author in scholarly.authors),
        title_source=scholarly.title.source,
        doi_source=scholarly.doi.source,
    )


def _collect_records(
    candidate: CandidateMetadata,
    sources: Sequence[MetadataSource],
) -> tuple[tuple[SourceRecord, ...], tuple[MetadataEvidence, ...]]:
    records: list[SourceRecord] = []
    evidence: list[MetadataEvidence] = []
    for source in sources:
        try:
            found = (
                (source.lookup_doi(candidate.doi),)
                if candidate.doi
                else source.search(candidate.title or "")
            )
            matched_by = "doi" if candidate.doi else "title_search"
            for record in found:
                if record is not None:
                    records.append(record)
                    evidence.append(
                        MetadataEvidence(
                            source=record.source,
                            source_id=record.source_id,
                            matched_by=matched_by,
                            record=record,
                        )
                    )
        except MetadataSourceError as exc:
            evidence.append(
                MetadataEvidence(
                    source=source.source,
                    source_id=None,
                    matched_by="doi" if candidate.doi else "title_search",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
    return tuple(records), tuple(evidence)


def _score(record: SourceRecord, candidate: CandidateMetadata) -> _ScoredRecord:
    doi_match = bool(candidate.doi and normalize_doi(record.doi) == candidate.doi)
    title_score = title_similarity(candidate.title, record.title)
    author_score = author_overlap(
        candidate.authors, [author.display_name for author in record.authors]
    )
    if doi_match:
        score = 0.65 + 0.25 * title_score + 0.10 * author_score
    else:
        score = 0.75 * title_score + 0.25 * author_score
    if record.work_type in JOURNAL_RECORD_TYPES:
        score += JOURNAL_RECORD_BONUS
    return _ScoredRecord(record, score, title_score, author_score, doi_match)


def _resolve(
    candidate: CandidateMetadata,
    scored: tuple[_ScoredRecord, ...],
    evidence: tuple[MetadataEvidence, ...],
) -> ResolutionResult:
    enriched_evidence = tuple(_replace_evidence(item, scored) for item in evidence)
    if not scored:
        return _unverified(candidate, enriched_evidence)

    groups = _groups(scored)
    ranked = sorted(groups.values(), key=_group_score, reverse=True)
    best = ranked[0]
    conflicts: list[str] = []
    if candidate.doi:
        incompatible = [
            item for item in best if item.title_score < DOI_TITLE_COMPATIBILITY
        ]
        if incompatible:
            conflicts.append(
                "Candidate DOI resolved externally, but the source title is incompatible."
            )
            return _conflict(candidate, enriched_evidence, tuple(conflicts))

    if (
        len(ranked) > 1
        and _group_score(best) - _group_score(ranked[1]) < AMBIGUITY_MARGIN
    ):
        conflicts.append(
            "Multiple external title-search candidates have indistinguishable scores."
        )
        return _conflict(candidate, enriched_evidence, tuple(conflicts))

    independent_sources = {item.record.source for item in best}
    strong = (
        len(independent_sources) >= 2 and _group_score(best) >= STRONG_AGREED_SCORE
    ) or (
        len(independent_sources) == 1
        and _group_score(best) >= STRONG_SINGLE_SOURCE_SCORE
    )
    if not strong:
        return _unverified(candidate, enriched_evidence)

    confidence = Confidence.HIGH if len(independent_sources) >= 2 else Confidence.MEDIUM
    metadata = _canonical_from_group(best, confidence)
    status = (
        ResolutionStatus.RESOLVED
        if len(independent_sources) >= 2
        else ResolutionStatus.PARTIALLY_RESOLVED
    )
    return ResolutionResult(
        status=status,
        metadata=metadata,
        candidate=candidate,
        evidence=enriched_evidence,
    )


def _groups(scored: Iterable[_ScoredRecord]) -> dict[str, list[_ScoredRecord]]:
    groups: dict[str, list[_ScoredRecord]] = defaultdict(list)
    for item in scored:
        identifier = (
            normalize_doi(item.record.doi)
            or f"{item.record.source}:{item.record.source_id}"
        )
        groups[identifier].append(item)
    return groups


def _group_score(group: Sequence[_ScoredRecord]) -> float:
    return sum(item.score for item in group) / len(group)


def _replace_evidence(
    evidence: MetadataEvidence,
    scored: Sequence[_ScoredRecord],
) -> MetadataEvidence:
    if evidence.record is None:
        return evidence
    item = next(
        (
            candidate
            for candidate in scored
            if candidate.record.source == evidence.record.source
            and candidate.record.source_id == evidence.record.source_id
        ),
        None,
    )
    if item is None:
        return evidence
    return MetadataEvidence(
        source=evidence.source,
        source_id=evidence.source_id,
        matched_by=evidence.matched_by,
        title_similarity=round(item.title_score, 3),
        author_overlap=round(item.author_score, 3),
        doi_match=item.doi_match,
        record=evidence.record,
    )


def _canonical_from_group(
    group: Sequence[_ScoredRecord],
    confidence: Confidence,
) -> CanonicalPaperMetadata:
    ordered = sorted(group, key=lambda item: item.record.source)
    primary = ordered[0].record
    provenance = tuple(
        MetadataProvenance(item.record.source, item.record.source_id)
        for item in ordered
    )
    authors = tuple(
        CanonicalAuthor(
            display_name=author.display_name,
            given_name=author.given_name,
            family_name=author.family_name,
            provenance=provenance,
        )
        for author in primary.authors
    )
    identifiers = {
        key: value
        for item in ordered
        for key, value in item.record.identifiers.items()
        if value
    }
    if primary.doi:
        identifiers["doi"] = primary.doi
    return CanonicalPaperMetadata(
        title=CanonicalValue(primary.title, confidence, provenance),
        doi=CanonicalValue(normalize_doi(primary.doi), confidence, provenance),
        authors=authors,
        year=CanonicalValue(primary.year, confidence, provenance),
        venue=CanonicalVenue(
            name=primary.venue,
            publisher=primary.publisher,
            volume=primary.volume,
            issue=primary.issue,
            pages=primary.pages,
            provenance=provenance,
        ),
        identifiers=identifiers,
    )


def _unverified(
    candidate: CandidateMetadata,
    evidence: tuple[MetadataEvidence, ...],
) -> ResolutionResult:
    provenance = tuple(
        MetadataProvenance(source, None)
        for source in (candidate.title_source, candidate.doi_source)
        if source
    )
    return ResolutionResult(
        status=ResolutionStatus.UNVERIFIED,
        metadata=CanonicalPaperMetadata(
            title=CanonicalValue(candidate.title, Confidence.LOW, provenance),
            doi=CanonicalValue(candidate.doi, Confidence.LOW, provenance),
            authors=tuple(
                CanonicalAuthor(name, provenance=provenance)
                for name in candidate.authors
            ),
            year=CanonicalValue(None, Confidence.LOW),
            venue=CanonicalVenue(None),
            identifiers={"doi": candidate.doi} if candidate.doi else {},
        ),
        candidate=candidate,
        evidence=evidence,
    )


def _conflict(
    candidate: CandidateMetadata,
    evidence: tuple[MetadataEvidence, ...],
    conflicts: tuple[str, ...],
) -> ResolutionResult:
    unresolved = _unverified(candidate, evidence)
    return ResolutionResult(
        status=ResolutionStatus.CONFLICT,
        metadata=unresolved.metadata,
        candidate=candidate,
        evidence=evidence,
        conflicts=conflicts,
    )
