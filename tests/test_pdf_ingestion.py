from pathlib import Path

import pytest

from paper_knowledge_base.ingestion.pdf import calculate_sha256, inspect_pdf


def test_calculate_sha256(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"example pdf content")

    digest = calculate_sha256(pdf_path)

    assert len(digest) == 64
    assert digest == calculate_sha256(pdf_path)


def test_inspect_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    content = b"fake pdf content"
    pdf_path.write_bytes(content)

    info = inspect_pdf(pdf_path)

    assert info.filename == "paper.pdf"
    assert info.size_bytes == len(content)
    assert len(info.sha256) == 64
    assert info.path == pdf_path.resolve()


def test_inspect_pdf_missing_file(tmp_path: Path) -> None:
    pdf_path = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        inspect_pdf(pdf_path)


def test_inspect_pdf_rejects_non_pdf(tmp_path: Path) -> None:
    text_path = tmp_path / "paper.txt"
    text_path.write_text("not a pdf")

    with pytest.raises(ValueError, match="not a PDF"):
        inspect_pdf(text_path)


def test_inspect_pdf_rejects_empty_file(tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.touch()

    with pytest.raises(ValueError, match="empty"):
        inspect_pdf(pdf_path)
