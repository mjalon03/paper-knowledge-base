"""Inspectable results produced by the conservative content-quality pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from paper_knowledge_base.content.models import (
    Citation,
    ContentProvenance,
    PaperContent,
)


class QualitySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class WarningCode(str, Enum):
    SUSPICIOUS_SECTION = "suspicious_section"
    DUPLICATE_SECTION = "duplicate_section"
    REPEATED_HEADER = "repeated_header"
    REPEATED_FOOTER = "repeated_footer"
    PICTURE_NOISE = "picture_noise"
    FIGURE_WITHOUT_CAPTION = "figure_without_caption"
    TABLE_WITHOUT_CAPTION = "table_without_caption"
    CAPTION_WITHOUT_FIGURE = "caption_without_figure"
    ORDER_ANOMALY = "order_anomaly"
    CITATION_LINK_MISSING = "citation_link_missing"
    CITATION_OFFSET_INVALID = "citation_offset_invalid"
    HIERARCHY_ANOMALY = "hierarchy_anomaly"
    POSSIBLE_DUPLICATE_BLOCK = "possible_duplicate_block"
    SOURCE_LOCATION_MISSING = "source_location_missing"


class TransformationAction(str, Enum):
    NORMALIZE_SECTION_HEADING = "normalize_section_heading"
    HIDE_SECTION_HEADING = "hide_section_heading"
    REMOVE_EMPTY_SECTION = "remove_empty_section"
    MERGE_DUPLICATE_SECTION = "merge_duplicate_section"
    SUPPRESS_REPEATED_PAGE_NOISE = "suppress_repeated_page_noise"
    SUPPRESS_DUPLICATE_BLOCK = "suppress_duplicate_block"
    SUPPRESS_EMPTY_BLOCK = "suppress_empty_block"
    SUPPRESS_PICTURE = "suppress_picture"
    ASSOCIATE_CAPTION = "associate_caption"


class FigureCategory(str, Enum):
    SCIENTIFIC_FIGURE = "scientific_figure"
    TABLE_IMAGE = "table_image"
    DECORATIVE = "decorative"
    LOGO = "logo"
    ICON = "icon"
    UNKNOWN = "unknown"


@dataclass(frozen=True, kw_only=True)
class ContentWarning:
    code: WarningCode
    severity: QualitySeverity
    message: str
    block_id: str | None = None
    section_id: str | None = None
    figure_id: str | None = None
    provenance: tuple[ContentProvenance, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ContentTransformation:
    action: TransformationAction
    target_id: str
    reason: str
    confidence: float
    evidence: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class FigureAssessment:
    figure_id: str
    category: FigureCategory
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class CaptionAssociation:
    content_id: str
    caption_source_id: str | None
    source: str
    confidence: float
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ContentQualityMetrics:
    raw_section_count: int
    clean_section_count: int
    raw_block_count: int
    clean_block_count: int
    raw_figure_count: int
    clean_figure_count: int
    removed_section_noise_count: int
    suppressed_picture_count: int
    duplicate_paragraph_count: int
    header_footer_removed_count: int
    warning_count: int
    citation_resolution_rate: float
    source_location_coverage: float


@dataclass(frozen=True, kw_only=True)
class ContentQualityResult:
    """The raw/clean pair plus an auditable account of quality processing."""

    source_content: PaperContent
    content: PaperContent
    warnings: tuple[ContentWarning, ...]
    transformations: tuple[ContentTransformation, ...]
    metrics: ContentQualityMetrics
    figure_assessments: tuple[FigureAssessment, ...] = ()
    caption_associations: tuple[CaptionAssociation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content.to_dict(),
            "figure_assessments": [
                _primitive(item) for item in self.figure_assessments
            ],
            "caption_associations": [
                _primitive(item) for item in self.caption_associations
            ],
            "metrics": _primitive(self.metrics),
            "transformations": [_primitive(item) for item in self.transformations],
            "warnings": [_primitive(item) for item in self.warnings],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True
        )


def citation_is_valid(citation: Citation, content: PaperContent) -> bool:
    reference_ids = {item.id for item in content.references}
    return all(reference_id in reference_ids for reference_id in citation.reference_ids)


def _primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _primitive(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    raise TypeError(f"unsupported quality value: {type(value).__name__}")
