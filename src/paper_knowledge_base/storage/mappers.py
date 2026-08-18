"""Small serialization/mapping helpers between domain and storage values."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from paper_knowledge_base.metadata.models import ResolutionResult
from paper_knowledge_base.processing.models import PaperProcessingResult


def resolution_to_json(result: ResolutionResult) -> dict[str, Any]:
    """Persist useful resolution evidence without raw parser/API payloads."""

    metadata = result.metadata
    return {
        "status": result.status.value,
        "candidate": _json_value(result.candidate),
        "metadata": {
            "title": _json_value(metadata.title),
            "doi": _json_value(metadata.doi),
            "year": _json_value(metadata.year),
            "venue": _json_value(metadata.venue),
            "authors": _json_value(metadata.authors),
            "identifiers": dict(metadata.identifiers),
        },
        "evidence": [
            {
                "source": evidence.source,
                "source_id": evidence.source_id,
                "matched_by": evidence.matched_by,
                "title_similarity": evidence.title_similarity,
                "author_overlap": evidence.author_overlap,
                "doi_match": evidence.doi_match,
                "year_match": evidence.year_match,
                "record": _source_record_without_raw(evidence.record),
                "error_type": evidence.error_type,
                "error_message": evidence.error_message,
            }
            for evidence in result.evidence
        ],
        "conflicts": list(result.conflicts),
    }


def processing_to_json(result: PaperProcessingResult) -> dict[str, Any]:
    """Persist a compact processing history, never raw TEI/Docling payloads."""

    return {
        "status": result.status.value,
        "route": result.route.value,
        "inspection": {
            "page_count": result.inspection.page_count,
            "text_character_count": result.inspection.text_character_count,
            "has_usable_embedded_text": result.inspection.has_usable_embedded_text,
        },
        "parser_runs": {
            name: {
                "status": run.status.value,
                "runtime_seconds": run.runtime_seconds,
                "version": run.version,
                "error_type": run.error_type,
                "error_message": run.error_message,
            }
            for name, run in result.parser_runs.items()
        },
    }


def canonical_paper_values(result: ResolutionResult) -> dict[str, Any]:
    """Flatten frequently queried canonical fields for a Paper row."""

    metadata = result.metadata
    return {
        "canonical_title": _string_or_none(metadata.title.value),
        "normalized_title": _normalized_title(metadata.title.value),
        "doi": _string_or_none(metadata.doi.value),
        "publication_year": _int_or_none(metadata.year.value),
        "venue_name": metadata.venue.name,
        "publisher": metadata.venue.publisher,
        "volume": metadata.venue.volume,
        "issue": metadata.venue.issue,
        "pages": metadata.venue.pages,
        "canonical_confidence": metadata.title.confidence.value,
        "metadata_provenance_json": {
            "title": [asdict(item) for item in metadata.title.provenance],
            "doi": [asdict(item) for item in metadata.doi.provenance],
            "year": [asdict(item) for item in metadata.year.provenance],
            "venue": [asdict(item) for item in metadata.venue.provenance],
        },
    }


def canonical_authors(result: ResolutionResult) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "display_name": author.display_name,
            "given_name": author.given_name,
            "family_name": author.family_name,
            "normalized_name": _normalized_author(author.display_name),
            "provenance_json": {
                "sources": [asdict(item) for item in author.provenance]
            },
        }
        for author in result.metadata.authors
    )


def identity_to_json(identity: Any) -> dict[str, Any]:
    """Serialize an identity decision without coupling ORM models to identity."""

    return {
        "relationship": identity.relationship.value,
        "confidence": identity.confidence.value,
        "score": identity.score,
        "title_similarity": identity.title_similarity,
        "author_similarity": identity.author_similarity,
        "doi_match": identity.doi_match,
        "year_match": identity.year_match,
        "provenance": list(identity.provenance),
        "reasons": list(identity.reasons),
        "conflicts": list(identity.conflicts),
        "evidence": [
            {
                "signal": evidence.signal.value,
                "detail": evidence.detail,
                "value": evidence.value,
                "positive": evidence.positive,
            }
            for evidence in identity.evidence
        ],
    }


def _source_record_without_raw(record: Any) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "source": record.source,
        "source_id": record.source_id,
        "doi": record.doi,
        "title": record.title,
        "authors": _json_value(record.authors),
        "year": record.year,
        "venue": record.venue,
        "publisher": record.publisher,
        "volume": record.volume,
        "issue": record.issue,
        "pages": record.pages,
        "work_type": record.work_type,
        "identifiers": dict(record.identifiers),
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _normalized_title(value: str | None) -> str | None:
    if value is None:
        return None
    from paper_knowledge_base.metadata.normalization import normalize_title

    return normalize_title(value) or None


def _normalized_author(value: str) -> str:
    from paper_knowledge_base.metadata.normalization import normalize_author_name

    return normalize_author_name(value)


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
