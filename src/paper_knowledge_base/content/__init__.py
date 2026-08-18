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

__all__ = [
    "BlockType",
    "BoundingBox",
    "Citation",
    "ContentBlock",
    "ContentProvenance",
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
]
