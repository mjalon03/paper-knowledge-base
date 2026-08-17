from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from paper_knowledge_base.extraction.pdf_layout import (
    PDFLayoutDocument,
    PDFPageLayout,
    TextBlock,
)


class PageLayoutType(str, Enum):
    SINGLE_COLUMN = "single_column"
    TWO_COLUMN = "two_column"


class BlockColumn(str, Enum):
    FULL_WIDTH = "full_width"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class OrderedTextBlock:
    block: TextBlock
    column: BlockColumn
    text: str


@dataclass(frozen=True)
class OrderedPageText:
    page_number: int
    layout_type: PageLayoutType
    blocks: tuple[OrderedTextBlock, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks if block.text.strip())


@dataclass(frozen=True)
class OrderedDocumentText:
    pages: tuple[OrderedPageText, ...]

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


def block_text(block: TextBlock) -> str:
    lines: list[str] = []

    for line in block.lines:
        text = "".join(span.text for span in line.spans).strip()

        if text:
            lines.append(text)

    return "\n".join(lines)


def classify_block_column(
    block: TextBlock,
    page_width: float,
) -> BlockColumn:
    midpoint = page_width / 2
    block_width = block.bbox.x1 - block.bbox.x0

    crosses_midpoint = block.bbox.x0 < midpoint < block.bbox.x1
    is_wide = block_width >= page_width * 0.65

    if crosses_midpoint and is_wide:
        return BlockColumn.FULL_WIDTH

    block_center = (block.bbox.x0 + block.bbox.x1) / 2

    if block_center < midpoint:
        return BlockColumn.LEFT

    return BlockColumn.RIGHT


def detect_page_layout(page: PDFPageLayout) -> PageLayoutType:
    left_blocks = 0
    right_blocks = 0

    for block in page.blocks:
        text = block_text(block).strip()

        # Ignore tiny labels, page numbers, etc. when detecting columns.
        if len(text) < 40:
            continue

        column = classify_block_column(block, page.width)

        if column == BlockColumn.LEFT:
            left_blocks += 1
        elif column == BlockColumn.RIGHT:
            right_blocks += 1

    if left_blocks >= 2 and right_blocks >= 2:
        return PageLayoutType.TWO_COLUMN

    return PageLayoutType.SINGLE_COLUMN


def _sort_top_to_bottom(
    blocks: list[OrderedTextBlock],
) -> list[OrderedTextBlock]:
    return sorted(
        blocks,
        key=lambda item: (
            item.block.bbox.y0,
            item.block.bbox.x0,
        ),
    )


def _order_two_column_region(
    blocks: list[OrderedTextBlock],
) -> list[OrderedTextBlock]:
    left = [block for block in blocks if block.column == BlockColumn.LEFT]
    right = [block for block in blocks if block.column == BlockColumn.RIGHT]

    return _sort_top_to_bottom(left) + _sort_top_to_bottom(right)


def order_page_blocks(page: PDFPageLayout) -> OrderedPageText:
    layout_type = detect_page_layout(page)

    classified = [
        OrderedTextBlock(
            block=block,
            column=classify_block_column(block, page.width),
            text=block_text(block),
        )
        for block in page.blocks
        if block_text(block).strip()
    ]

    if layout_type == PageLayoutType.SINGLE_COLUMN:
        return OrderedPageText(
            page_number=page.page_number,
            layout_type=layout_type,
            blocks=tuple(_sort_top_to_bottom(classified)),
        )

    full_width = _sort_top_to_bottom(
        [block for block in classified if block.column == BlockColumn.FULL_WIDTH]
    )

    column_blocks = [
        block for block in classified if block.column != BlockColumn.FULL_WIDTH
    ]

    ordered: list[OrderedTextBlock] = []
    remaining = column_blocks.copy()

    for wide_block in full_width:
        above = [
            block
            for block in remaining
            if block.block.bbox.y0 < wide_block.block.bbox.y0
        ]

        ordered.extend(_order_two_column_region(above))

        remaining = [block for block in remaining if block not in above]

        ordered.append(wide_block)

    ordered.extend(_order_two_column_region(remaining))

    return OrderedPageText(
        page_number=page.page_number,
        layout_type=layout_type,
        blocks=tuple(ordered),
    )


def reconstruct_reading_order(
    document: PDFLayoutDocument,
) -> OrderedDocumentText:
    return OrderedDocumentText(
        pages=tuple(order_page_blocks(page) for page in document.pages)
    )
