from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PDFFileInfo:
    path: Path
    filename: str
    size_bytes: int
    sha256: str


def calculate_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)

    return digest.hexdigest()


def inspect_pdf(path: str | Path) -> PDFFileInfo:
    pdf_path = Path(path).expanduser().resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise ValueError(f"Path is not a file: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"File is not a PDF: {pdf_path}")

    size_bytes = pdf_path.stat().st_size

    if size_bytes == 0:
        raise ValueError(f"PDF file is empty: {pdf_path}")

    return PDFFileInfo(
        path=pdf_path,
        filename=pdf_path.name,
        size_bytes=size_bytes,
        sha256=calculate_sha256(pdf_path),
    )
