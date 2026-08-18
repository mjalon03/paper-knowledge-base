"""Lightweight PDF inspection for parser routing, not scholarly extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paper_knowledge_base.extraction.pdf_text import extract_pdf_text
from paper_knowledge_base.processing.models import PDFInspection


@dataclass(frozen=True)
class TextCoverageThresholds:
    """Conservative routing thresholds for usable selectable PDF text.

    A PDF needs enough total text, at least one substantial text page, and a
    meaningful average. This prevents a tiny stray text layer from being routed
    as a born-digital document; it is deliberately not an OCR-quality metric.
    """

    minimum_total_characters: int = 300
    minimum_page_characters: int = 80
    minimum_average_characters_per_page: float = 150.0


DEFAULT_TEXT_COVERAGE_THRESHOLDS = TextCoverageThresholds()


def inspect_embedded_text(
    path: str | Path,
    *,
    thresholds: TextCoverageThresholds = DEFAULT_TEXT_COVERAGE_THRESHOLDS,
) -> PDFInspection:
    document = extract_pdf_text(path)
    page_lengths = [len("".join(page.text.split())) for page in document.pages]
    text_character_count = sum(page_lengths)
    meaningful_pages = sum(
        length >= thresholds.minimum_page_characters for length in page_lengths
    )
    page_count = document.page_count
    average = text_character_count / page_count if page_count else 0.0
    ratio = meaningful_pages / page_count if page_count else 0.0
    usable = (
        text_character_count >= thresholds.minimum_total_characters
        and meaningful_pages > 0
        and average >= thresholds.minimum_average_characters_per_page
    )
    return PDFInspection(
        page_count=page_count,
        text_character_count=text_character_count,
        pages_with_meaningful_text=meaningful_pages,
        text_page_ratio=ratio,
        average_characters_per_page=average,
        has_usable_embedded_text=usable,
    )
