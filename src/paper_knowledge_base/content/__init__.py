"""Canonical paper-content domain layer."""

from paper_knowledge_base.content.builder import build_paper_content
from paper_knowledge_base.content.models import (
    BlockType,
    BoundingBox,
    Citation,
    ContentBlock,
    ContentProvenance,
    ContentStatus,
    Equation,
    Figure,
    PaperContent,
    Paragraph,
    Reference,
    Section,
    SourceLocation,
    Table,
)
from paper_knowledge_base.content.quality import (
    ContentQualityResult,
    improve_content_quality,
    normalize_paper_content,
)

__all__ = [
    "BlockType",
    "BoundingBox",
    "Citation",
    "ContentBlock",
    "ContentProvenance",
    "ContentQualityResult",
    "ContentStatus",
    "Equation",
    "Figure",
    "PaperContent",
    "Paragraph",
    "Reference",
    "Section",
    "SourceLocation",
    "Table",
    "build_paper_content",
    "improve_content_quality",
    "normalize_paper_content",
]
