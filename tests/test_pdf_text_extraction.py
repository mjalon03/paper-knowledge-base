from pathlib import Path

import pymupdf
import pytest

from paper_knowledge_base.extraction.pdf_text import (
    PDFExtractionError,
    extract_pdf_text,
)


def create_test_pdf(path: Path) -> None:
    document = pymupdf.open()

    page1 = document.new_page()
    page1.insert_text((72, 72), "First page text")

    page2 = document.new_page()
    page2.insert_text((72, 72), "Second page text")

    document.save(path)
    document.close()


def test_extract_pdf_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_test_pdf(pdf_path)

    result = extract_pdf_text(pdf_path)

    assert result.page_count == 2
    assert len(result.pages) == 2

    assert result.pages[0].page_number == 1
    assert "First page text" in result.pages[0].text

    assert result.pages[1].page_number == 2
    assert "Second page text" in result.pages[1].text


def test_full_text_combines_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_test_pdf(pdf_path)

    result = extract_pdf_text(pdf_path)

    assert "First page text" in result.full_text
    assert "Second page text" in result.full_text


def test_extract_blank_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"

    document = pymupdf.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    result = extract_pdf_text(pdf_path)

    assert result.page_count == 1
    assert result.pages[0].text == ""


def test_rejects_invalid_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invalid.pdf"
    pdf_path.write_text("This is not a real PDF.")

    with pytest.raises(PDFExtractionError):
        extract_pdf_text(pdf_path)
