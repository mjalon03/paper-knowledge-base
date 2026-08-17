from paper_knowledge_base.extraction.pdf_layout import (
    BoundingBox,
    PDFPageLayout,
    TextBlock,
    TextLine,
    TextSpan,
)
from paper_knowledge_base.extraction.reading_order import (
    BlockColumn,
    PageLayoutType,
    classify_block_column,
    detect_page_layout,
    order_page_blocks,
)


def make_block(
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> TextBlock:
    bbox = BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1)

    span = TextSpan(
        text=text,
        bbox=bbox,
        font_size=10,
        font_name="Helvetica",
        flags=0,
        bold=False,
        italic=False,
    )

    line = TextLine(
        bbox=bbox,
        direction=(1.0, 0.0),
        spans=(span,),
    )

    return TextBlock(
        bbox=bbox,
        lines=(line,),
    )


def test_classify_full_width_block() -> None:
    block = make_block(
        "Full width title",
        50,
        50,
        550,
        80,
    )

    result = classify_block_column(block, page_width=600)

    assert result == BlockColumn.FULL_WIDTH


def test_classify_left_and_right_blocks() -> None:
    left = make_block(
        "Left column",
        50,
        100,
        280,
        150,
    )

    right = make_block(
        "Right column",
        320,
        100,
        550,
        150,
    )

    assert classify_block_column(left, 600) == BlockColumn.LEFT

    assert classify_block_column(right, 600) == BlockColumn.RIGHT


def test_detect_two_column_layout() -> None:
    page = PDFPageLayout(
        page_number=1,
        width=600,
        height=800,
        blocks=(
            make_block(
                "Left column paragraph one with enough text to count.",
                50,
                100,
                280,
                180,
            ),
            make_block(
                "Left column paragraph two with enough text to count.",
                50,
                200,
                280,
                280,
            ),
            make_block(
                "Right column paragraph one with enough text to count.",
                320,
                100,
                550,
                180,
            ),
            make_block(
                "Right column paragraph two with enough text to count.",
                320,
                200,
                550,
                280,
            ),
        ),
    )

    assert detect_page_layout(page) == PageLayoutType.TWO_COLUMN


def test_two_column_reading_order() -> None:
    page = PDFPageLayout(
        page_number=1,
        width=600,
        height=800,
        blocks=(
            make_block(
                "Right paragraph two with enough text for detection.",
                320,
                300,
                550,
                370,
            ),
            make_block(
                "Left paragraph two with enough text for detection.",
                50,
                300,
                280,
                370,
            ),
            make_block(
                "Right paragraph one with enough text for detection.",
                320,
                150,
                550,
                220,
            ),
            make_block(
                "Left paragraph one with enough text for detection.",
                50,
                150,
                280,
                220,
            ),
        ),
    )

    result = order_page_blocks(page)

    texts = [block.text for block in result.blocks]

    assert result.layout_type == PageLayoutType.TWO_COLUMN
    assert texts == [
        "Left paragraph one with enough text for detection.",
        "Left paragraph two with enough text for detection.",
        "Right paragraph one with enough text for detection.",
        "Right paragraph two with enough text for detection.",
    ]


def test_full_width_title_precedes_columns() -> None:
    page = PDFPageLayout(
        page_number=1,
        width=600,
        height=800,
        blocks=(
            make_block(
                "Example Paper Title",
                50,
                40,
                550,
                80,
            ),
            make_block(
                "Left paragraph one with enough text for detection.",
                50,
                150,
                280,
                220,
            ),
            make_block(
                "Left paragraph two with enough text for detection.",
                50,
                250,
                280,
                320,
            ),
            make_block(
                "Right paragraph one with enough text for detection.",
                320,
                150,
                550,
                220,
            ),
            make_block(
                "Right paragraph two with enough text for detection.",
                320,
                250,
                550,
                320,
            ),
        ),
    )

    result = order_page_blocks(page)

    assert result.blocks[0].text == "Example Paper Title"
