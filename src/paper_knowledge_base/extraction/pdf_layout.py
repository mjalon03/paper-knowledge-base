from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from paper_knowledge_base.ingestion.pdf import inspect_pdf


class PDFLayoutExtractionError(Exception):
    """Raised when layout information cannot be extracted from a PDF."""


@dataclass(frozen=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class TextSpan:
    text: str
    bbox: BoundingBox
    font_size: float
    font_name: str
    flags: int
    bold: bool
    italic: bool


@dataclass(frozen=True)
class TextLine:
    bbox: BoundingBox
    direction: tuple[float, float]
    spans: tuple[TextSpan, ...]


@dataclass(frozen=True)
class TextBlock:
    bbox: BoundingBox
    lines: tuple[TextLine, ...]


@dataclass(frozen=True)
class PDFPageLayout:
    page_number: int
    width: float
    height: float
    blocks: tuple[TextBlock, ...]


@dataclass(frozen=True)
class PDFLayoutDocument:
    path: Path
    page_count: int
    pages: tuple[PDFPageLayout, ...]


def _bbox(values: tuple[float, float, float, float]) -> BoundingBox:
    return BoundingBox(
        x0=float(values[0]),
        y0=float(values[1]),
        x1=float(values[2]),
        y1=float(values[3]),
    )


def _is_bold(flags: int) -> bool:
    return bool(flags & (1 << 4))


def _is_italic(flags: int) -> bool:
    return bool(flags & (1 << 1))


def extract_pdf_layout(path: str | Path) -> PDFLayoutDocument:
    file_info = inspect_pdf(path)

    try:
        with pymupdf.open(file_info.path) as document:
            pages: list[PDFPageLayout] = []

            for page in document:
                raw = page.get_text("dict", sort=False)

                blocks: list[TextBlock] = []

                for block in raw["blocks"]:
                    # type == 0 means text block.
                    if block["type"] != 0:
                        continue

                    lines: list[TextLine] = []

                    for line in block["lines"]:
                        spans: list[TextSpan] = []

                        for span in line["spans"]:
                            flags = int(span["flags"])

                            spans.append(
                                TextSpan(
                                    text=span["text"],
                                    bbox=_bbox(span["bbox"]),
                                    font_size=float(span["size"]),
                                    font_name=span["font"],
                                    flags=flags,
                                    bold=_is_bold(flags),
                                    italic=_is_italic(flags),
                                )
                            )

                        lines.append(
                            TextLine(
                                bbox=_bbox(line["bbox"]),
                                direction=(
                                    float(line["dir"][0]),
                                    float(line["dir"][1]),
                                ),
                                spans=tuple(spans),
                            )
                        )

                    blocks.append(
                        TextBlock(
                            bbox=_bbox(block["bbox"]),
                            lines=tuple(lines),
                        )
                    )

                pages.append(
                    PDFPageLayout(
                        page_number=page.number + 1,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        blocks=tuple(blocks),
                    )
                )

            return PDFLayoutDocument(
                path=file_info.path,
                page_count=document.page_count,
                pages=tuple(pages),
            )

    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise PDFLayoutExtractionError(
            f"Failed to extract layout from PDF: {file_info.path}"
        ) from exc
