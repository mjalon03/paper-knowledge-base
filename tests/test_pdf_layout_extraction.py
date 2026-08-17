from pathlib import Path

import pymupdf
import pytest

from paper_knowledge_base.extraction.pdf_layout import (
    PDFLayoutExtractionError,
    _is_bold,
    _is_italic,
    extract_pdf_layout,
)


def create_layout_test_pdf(path: Path) -> None:
    document = pymupdf.open()

    page = document.new_page(width=600, height=800)

    page.insert_text(
        (72, 80),
        "Example Paper Title",
        fontsize=20,
    )

    page.insert_text(
        (72, 120),
        "This is the first paragraph.",
        fontsize=11,
    )

    page.insert_text(
        (320, 120),
        "This is the second column.",
        fontsize=11,
    )

    document.save(path)
    document.close()


def test_extract_pdf_layout(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_layout_test_pdf(pdf_path)

    result = extract_pdf_layout(pdf_path)

    assert result.page_count == 1
    assert len(result.pages) == 1

    page = result.pages[0]

    assert page.page_number == 1
    assert page.width == pytest.approx(600)
    assert page.height == pytest.approx(800)
    assert len(page.blocks) > 0


def test_layout_contains_text_spans(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_layout_test_pdf(pdf_path)

    result = extract_pdf_layout(pdf_path)

    spans = [
        span
        for block in result.pages[0].blocks
        for line in block.lines
        for span in line.spans
    ]

    texts = [span.text for span in spans]

    assert any("Example Paper Title" in text for text in texts)
    assert any("first paragraph" in text for text in texts)
    assert any("second column" in text for text in texts)


def test_layout_preserves_font_size(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_layout_test_pdf(pdf_path)

    result = extract_pdf_layout(pdf_path)

    spans = [
        span
        for block in result.pages[0].blocks
        for line in block.lines
        for span in line.spans
    ]

    title_span = next(span for span in spans if "Example Paper Title" in span.text)

    assert title_span.font_size == pytest.approx(20)


def test_layout_preserves_bounding_boxes(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_layout_test_pdf(pdf_path)

    result = extract_pdf_layout(pdf_path)

    spans = [
        span
        for block in result.pages[0].blocks
        for line in block.lines
        for span in line.spans
    ]

    for span in spans:
        assert span.bbox.x1 >= span.bbox.x0
        assert span.bbox.y1 >= span.bbox.y0


def test_font_flag_helpers() -> None:
    assert _is_italic(1 << 1)
    assert not _is_italic(0)

    assert _is_bold(1 << 4)
    assert not _is_bold(0)


def test_rejects_invalid_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invalid.pdf"
    pdf_path.write_text("This is not a real PDF.")

    with pytest.raises(PDFLayoutExtractionError):
        extract_pdf_layout(pdf_path)
