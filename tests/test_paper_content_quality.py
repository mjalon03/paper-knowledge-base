from __future__ import annotations

from dataclasses import replace

from paper_knowledge_base.content import (
    BoundingBox,
    Citation,
    ContentProvenance,
    ContentStatus,
    Figure,
    PaperContent,
    Paragraph,
    Reference,
    Section,
    SourceLocation,
    Table,
    improve_content_quality,
)
from paper_knowledge_base.content.quality.models import (
    FigureCategory,
    TransformationAction,
    WarningCode,
)

PROVENANCE = (ContentProvenance(parser="synthetic", source_element_id="source"),)


def _location(
    page: int, *, y0: float = 200, y1: float = 240, x0: float = 10, x1: float = 200
) -> SourceLocation:
    return SourceLocation(
        page_number=page,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, coordinate_origin="BOTTOMLEFT"),
        parser="synthetic",
        coordinate_system="synthetic-BOTTOMLEFT",
    )


def _paragraph(
    block_id: str,
    order: int,
    text: str,
    section_id: str = "s1",
    location: SourceLocation | None = None,
    *,
    citation_ids: tuple[str, ...] = (),
) -> Paragraph:
    return Paragraph(
        id=block_id,
        order=order,
        section_id=section_id,
        text=text,
        source_location=location,
        citation_ids=citation_ids,
        provenance=PROVENANCE,
    )


def _content(
    blocks: tuple = (),
    sections: tuple[Section, ...] | None = None,
    *,
    references: tuple[Reference, ...] = (),
    citations: tuple[Citation, ...] = (),
) -> PaperContent:
    sections = sections or (
        Section(
            id="s1",
            title="1 Introduction",
            label="1",
            level=1,
            order=0,
            block_ids=tuple(block.id for block in blocks if block.section_id == "s1"),
            provenance=PROVENANCE,
        ),
    )
    return PaperContent(
        source_document_sha256="a" * 64,
        sections=sections,
        blocks=blocks,
        references=references,
        citations=citations,
        status=ContentStatus.COMPLETE,
    )


def test_pipeline_keeps_raw_content_and_stable_ids() -> None:
    paragraph = _paragraph("p1", 0, "A stable paragraph.")
    raw = _content((paragraph,))

    result = improve_content_quality(raw)

    assert result.source_content is raw
    assert result.source_content == raw
    assert result.content.blocks[0].id == paragraph.id
    assert result.content.sections[0].id == raw.sections[0].id


def test_repeated_page_edges_are_suppressed_but_body_text_is_kept() -> None:
    blocks = (
        _paragraph(
            "h1",
            0,
            "Journal of Astrocyte Science",
            location=_location(1, y0=720, y1=740),
        ),
        _paragraph(
            "body1",
            1,
            "Repeated words in the body are not page noise.",
            location=_location(1),
        ),
        _paragraph("f1", 2, "12", location=_location(1, y0=20, y1=35)),
        _paragraph(
            "h2",
            3,
            "Journal of Astrocyte Science",
            location=_location(2, y0=720, y1=740),
        ),
        _paragraph("body2", 4, "A second body paragraph.", location=_location(2)),
        _paragraph("f2", 5, "12", location=_location(2, y0=20, y1=35)),
    )

    result = improve_content_quality(_content(blocks))
    ids = {block.id for block in result.content.blocks}

    assert ids == {"body1", "body2"}
    assert result.metrics.header_footer_removed_count == 4
    assert {warning.code for warning in result.warnings} >= {
        WarningCode.REPEATED_HEADER,
        WarningCode.REPEATED_FOOTER,
    }


def test_same_page_duplicate_requires_matching_geometry() -> None:
    blocks = (
        _paragraph("p1", 0, "Duplicate text", location=_location(1, x0=10, x1=200)),
        _paragraph("p2", 1, "Duplicate text", location=_location(1, x0=11, x1=201)),
        _paragraph("p3", 2, "Duplicate text", location=_location(2, x0=10, x1=200)),
    )

    result = improve_content_quality(_content(blocks))

    assert [block.id for block in result.content.ordered_blocks] == ["p1", "p3"]
    assert result.metrics.duplicate_paragraph_count == 1
    assert any(w.code is WarningCode.POSSIBLE_DUPLICATE_BLOCK for w in result.warnings)


def test_section_cleanup_normalizes_hides_merges_and_removes_empty_wrappers() -> None:
    sections = (
        Section(
            id="s1",
            title=". . Methods",
            label=None,
            level=1,
            order=0,
            block_ids=("p1",),
        ),
        Section(
            id="s2", title="Methods", label=None, level=1, order=1, block_ids=("p2",)
        ),
        Section(id="s3", title="FIGURE", label=None, level=1, order=2, block_ids=()),
        Section(
            id="s4",
            title="# d o w n l o a d --data",
            label=None,
            level=1,
            order=3,
            block_ids=("p3",),
        ),
    )
    blocks = (
        _paragraph("p1", 0, "One", section_id="s1"),
        _paragraph("p2", 1, "Two", section_id="s2"),
        _paragraph("p3", 2, "Code-adjacent content", section_id="s4"),
    )

    result = improve_content_quality(_content(blocks, sections))
    by_id = {section.id: section for section in result.content.sections}

    assert "s3" not in by_id
    assert by_id["s1"].title == "Methods"
    assert by_id["s4"].title == ""
    assert by_id["s4"].special == "quality_hidden_heading"
    assert "s2" not in by_id
    assert by_id["s1"].block_ids == ("p1", "p2")
    actions = {item.action for item in result.transformations}
    assert TransformationAction.NORMALIZE_SECTION_HEADING in actions
    assert TransformationAction.HIDE_SECTION_HEADING in actions
    assert TransformationAction.MERGE_DUPLICATE_SECTION in actions


def test_picture_policy_suppresses_small_noise_and_keeps_uncertain_science() -> None:
    figures = (
        Figure(
            id="f-small-1",
            order=0,
            section_id="s1",
            label="picture",
            source_location=_location(1, y0=10, y1=25, x0=0, x1=80),
            provenance=PROVENANCE,
        ),
        Figure(
            id="f-small-2",
            order=1,
            section_id="s1",
            label="picture",
            source_location=_location(2, y0=10, y1=25, x0=0, x1=80),
            provenance=PROVENANCE,
        ),
        Figure(
            id="f-large",
            order=2,
            section_id="s1",
            label="picture",
            source_location=_location(3, y0=200, y1=500, x0=10, x1=400),
            provenance=PROVENANCE,
        ),
    )

    result = improve_content_quality(_content(figures))
    ids = {block.id for block in result.content.blocks}

    assert ids == {"f-large"}
    assert result.metrics.suppressed_picture_count == 2
    assessment = next(
        item for item in result.figure_assessments if item.figure_id == "f-large"
    )
    assert assessment.category is FigureCategory.UNKNOWN
    assert any(w.code is WarningCode.FIGURE_WITHOUT_CAPTION for w in result.warnings)


def test_unique_nearby_caption_is_associated_and_caption_paragraph_removed() -> None:
    figure = Figure(
        id="f1",
        order=1,
        section_id="s1",
        label="Figure 1",
        source_location=_location(1, y0=250, y1=450, x0=10, x1=400),
        provenance=PROVENANCE,
    )
    caption = _paragraph(
        "caption1",
        2,
        "Figure 1. Calcium events across conditions.",
        location=_location(1, y0=200, y1=230),
    )

    result = improve_content_quality(_content((figure, caption)))
    clean_figure = result.content.blocks_by_id["f1"]

    assert isinstance(clean_figure, Figure)
    assert clean_figure.caption == caption.text
    assert "caption1" not in result.content.blocks_by_id
    assert result.caption_associations[0].source == "PROXIMITY"
    assert not any(
        w.code is WarningCode.FIGURE_WITHOUT_CAPTION for w in result.warnings
    )


def test_citation_diagnostics_report_missing_links_and_bad_offsets() -> None:
    paragraph = _paragraph("p1", 0, "Cites [1]", citation_ids=("c1",))
    citations = (
        Citation(
            id="c1",
            display="[1]",
            reference_ids=("missing",),
            block_id="p1",
            start=1,
            end=4,
        ),
    )
    result = improve_content_quality(_content((paragraph,), citations=citations))

    codes = {warning.code for warning in result.warnings}
    assert WarningCode.CITATION_LINK_MISSING in codes
    assert WarningCode.CITATION_OFFSET_INVALID in codes
    assert result.metrics.citation_resolution_rate == 0.0


def test_partial_content_with_tables_is_safe_and_serializable() -> None:
    table = Table(
        id="t1",
        order=0,
        section_id="s1",
        label="Table 1",
        headers=("A",),
        rows=(("1",),),
        provenance=PROVENANCE,
    )
    raw = replace(_content((table,)), status=ContentStatus.PARTIAL)

    result = improve_content_quality(raw)

    assert result.content.status is ContentStatus.PARTIAL
    assert result.to_json() == result.to_json()
    assert any(w.code is WarningCode.TABLE_WITHOUT_CAPTION for w in result.warnings)
