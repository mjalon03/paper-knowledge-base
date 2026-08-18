"""Parser-independent domain models for structured paper content.

The content package deliberately contains only project-owned dataclasses.  GROBID
TEI and Docling JSON are translated into these types at the parser boundary and
never appear in the public article representation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContentStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class BlockType(str, Enum):
    PARAGRAPH = "paragraph"
    FIGURE = "figure"
    TABLE = "table"
    EQUATION = "equation"


@dataclass(frozen=True, kw_only=True)
class BoundingBox:
    """A source bounding box with its original coordinate convention intact."""

    x0: float
    y0: float
    x1: float
    y1: float
    coordinate_origin: str | None = None


@dataclass(frozen=True, kw_only=True)
class SourceLocation:
    page_number: int | None = None
    bbox: BoundingBox | None = None
    parser: str | None = None
    source_element_id: str | None = None
    coordinate_system: str | None = None
    raw_coordinates: str | None = None


@dataclass(frozen=True, kw_only=True)
class ContentProvenance:
    parser: str
    source_element_id: str | None = None
    parser_version: str | None = None
    note: str | None = None


@dataclass(frozen=True, kw_only=True)
class Citation:
    id: str
    display: str
    reference_ids: tuple[str, ...]
    block_id: str | None = None
    start: int | None = None
    end: int | None = None
    provenance: tuple[ContentProvenance, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Reference:
    id: str
    label: str | None
    raw_text: str
    title: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    identifiers: dict[str, str] = field(default_factory=dict)
    provenance: tuple[ContentProvenance, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ContentBlock:
    id: str
    order: int
    section_id: str | None
    source_location: SourceLocation | None = None
    provenance: tuple[ContentProvenance, ...] = ()
    block_type: BlockType = BlockType.PARAGRAPH


@dataclass(frozen=True, kw_only=True)
class Paragraph(ContentBlock):
    text: str
    citation_ids: tuple[str, ...] = ()
    metadata_field: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_type", BlockType.PARAGRAPH)


@dataclass(frozen=True, kw_only=True)
class Figure(ContentBlock):
    label: str | None = None
    caption: str | None = None
    asset_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_type", BlockType.FIGURE)


@dataclass(frozen=True, kw_only=True)
class Table(ContentBlock):
    label: str | None = None
    caption: str | None = None
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    plain_text: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_type", BlockType.TABLE)


@dataclass(frozen=True, kw_only=True)
class Equation(ContentBlock):
    text: str | None = None
    latex: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_type", BlockType.EQUATION)


@dataclass(frozen=True, kw_only=True)
class Section:
    id: str
    title: str
    label: str | None
    level: int
    order: int
    parent_id: str | None = None
    block_ids: tuple[str, ...] = ()
    provenance: tuple[ContentProvenance, ...] = ()
    special: str | None = None


@dataclass(frozen=True, kw_only=True)
class PaperContent:
    """Canonical article body and its links back to a source document."""

    source_document_sha256: str | None
    sections: tuple[Section, ...]
    blocks: tuple[ContentBlock, ...]
    references: tuple[Reference, ...] = ()
    citations: tuple[Citation, ...] = ()
    status: ContentStatus = ContentStatus.FAILED
    warnings: tuple[str, ...] = ()
    schema_version: int = 1
    source_document_id: str | None = None

    @property
    def ordered_blocks(self) -> tuple[ContentBlock, ...]:
        """Return the stable mobile reading stream."""

        return tuple(sorted(self.blocks, key=lambda block: (block.order, block.id)))

    @property
    def blocks_by_id(self) -> dict[str, ContentBlock]:
        return {block.id: block for block in self.blocks}

    @property
    def citations_by_id(self) -> dict[str, Citation]:
        return {citation.id: citation for citation in self.citations}

    def to_dict(self) -> dict[str, Any]:
        """Return only JSON-compatible project-owned primitives."""

        return _primitive(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize deterministically without parser-native objects."""

        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


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
    raise TypeError(f"unsupported content value: {type(value).__name__}")


@dataclass(frozen=True, kw_only=True)
class ContentFragment:
    """Internal mapper output using canonical types before cross-parser merging."""

    parser: str
    parser_version: str | None
    sections: tuple[Section, ...] = ()
    blocks: tuple[ContentBlock, ...] = ()
    references: tuple[Reference, ...] = ()
    citations: tuple[Citation, ...] = ()
    warnings: tuple[str, ...] = ()
