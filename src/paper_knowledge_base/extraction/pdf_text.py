from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from paper_knowledge_base.ingestion.pdf import inspect_pdf


class PDFExtractionError(Exception):
    """Raised when text cannot be extracted from a PDF."""


@dataclass(frozen=True)
class PDFPageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class PDFTextDocument:
    path: Path
    page_count: int
    pages: tuple[PDFPageText, ...]

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


def extract_pdf_text(path: str | Path) -> PDFTextDocument:
    file_info = inspect_pdf(path)

    try:
        with pymupdf.open(file_info.path) as document:
            pages = tuple(
                PDFPageText(
                    page_number=page.number + 1,
                    text=page.get_text("text", sort=True).strip(),
                )
                for page in document
            )

            return PDFTextDocument(
                path=file_info.path,
                page_count=document.page_count,
                pages=pages,
            )

    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise PDFExtractionError(
            f"Failed to extract text from PDF: {file_info.path}"
        ) from exc
