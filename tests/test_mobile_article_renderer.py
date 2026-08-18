from __future__ import annotations

from paper_knowledge_base.content import (
    Citation,
    ContentStatus,
    Equation,
    Figure,
    PaperContent,
    Paragraph,
    Reference,
    Section,
    SourceLocation,
    Table,
)
from paper_knowledge_base.metadata.models import (
    CanonicalAuthor,
    CanonicalPaperMetadata,
    CanonicalValue,
    CanonicalVenue,
)
from paper_knowledge_base.rendering import (
    AssetReference,
    RenderOptions,
    render_mobile_article,
)


def _metadata(*, authors: tuple[str, ...] = ("Ada Author", "Bea Biologist")):
    return CanonicalPaperMetadata(
        title=CanonicalValue("A Ca²⁺ study", confidence="high"),
        doi=CanonicalValue("10.1000/example", confidence="high"),
        authors=tuple(CanonicalAuthor(name) for name in authors),
        year=CanonicalValue(2024, confidence="high"),
        venue=CanonicalVenue("Example Journal", publisher="Example Press"),
        identifiers={},
    )


def _content() -> PaperContent:
    sections = (
        Section(
            id="abstract",
            title="Abstract",
            label=None,
            level=0,
            order=0,
            special="derived_from_scholarly_metadata.abstract",
        ),
        Section(id="intro", title="Introduction", label="1", level=0, order=1),
        Section(id="methods", title="Methods", label="2", level=0, order=2),
        Section(
            id="deep",
            title="Imaging",
            label="2.1",
            level=1,
            order=3,
            parent_id="methods",
        ),
    )
    paragraph = Paragraph(
        id="p1",
        order=1,
        section_id="intro",
        text="Signal [1] uses <safe> <x>.",
        citation_ids=("c1", "missing"),
    )
    return PaperContent(
        source_document_sha256="a" * 64,
        source_document_id="doc-1",
        sections=sections,
        blocks=(
            Paragraph(
                id="abstract-block",
                order=0,
                section_id="abstract",
                text="Abstract Ca²⁺.",
            ),
            paragraph,
            Figure(
                id="fig1",
                order=2,
                section_id="methods",
                label="Figure 1",
                caption="A useful figure",
                asset_ref="asset-1",
            ),
            Table(
                id="table1",
                order=3,
                section_id="methods",
                label="Table 1",
                caption="Values",
                headers=("A", "B"),
                rows=(("1", "2"),),
            ),
            Equation(id="eq1", order=4, section_id="deep", latex=r"E < mc^2"),
        ),
        references=(
            Reference(
                id="ref-1",
                label="[1]",
                raw_text="Smith et al.",
                title="Reference title",
                doi="10.1000/ref",
            ),
        ),
        citations=(
            Citation(
                id="c1",
                display="[1]",
                reference_ids=("ref-1",),
                block_id="p1",
                start=7,
                end=10,
            ),
            Citation(
                id="missing",
                display="<x>",
                reference_ids=("nope",),
                block_id="p1",
                start=23,
                end=26,
            ),
        ),
        status=ContentStatus.COMPLETE,
    )


def test_header_abstract_toc_and_semantic_body_are_deterministic() -> None:
    rendered = render_mobile_article(_metadata(), _content())

    assert rendered == render_mobile_article(_metadata(), _content())
    assert rendered.count('<h1 id="paper-title">') == 1
    assert rendered.count("Abstract Ca²⁺.") == 1
    assert "<h2>Introduction</h2>" in rendered
    assert "<h2>Methods</h2>" in rendered
    assert "<h3>Imaging</h3>" in rendered
    assert 'href="#section-intro"' in rendered
    assert rendered.count('href="#section-deep"') == 1


def test_citations_escape_text_and_keep_unresolved_text_plain() -> None:
    rendered = render_mobile_article(_metadata(), _content())

    assert "&lt;safe&gt;" in rendered
    assert 'href="#ref-ref-1">[1]</a>' in rendered
    assert "&lt;x&gt;" in rendered
    assert 'href="#ref-nope"' not in rendered


def test_figures_tables_equations_and_source_metadata() -> None:
    content = _content()
    figure = content.blocks[2]
    located = Figure(
        id=figure.id,
        order=figure.order,
        section_id=figure.section_id,
        label=figure.label,
        caption=figure.caption,
        asset_ref=figure.asset_ref,
        source_location=SourceLocation(page_number=7),
    )
    content = PaperContent(
        source_document_sha256=content.source_document_sha256,
        source_document_id=content.source_document_id,
        sections=content.sections,
        blocks=(*content.blocks[:2], located, *content.blocks[3:]),
        references=content.references,
        citations=content.citations,
        status=content.status,
    )
    rendered = render_mobile_article(
        _metadata(),
        content,
        figure_resolver=lambda ref: AssetReference(
            identifier=ref, href="figures/one.png"
        ),
        debug=True,
        original_pdf_url="papers/example.pdf",
    )

    assert '<img src="figures/one.png"' in rendered
    assert '<div class="table-scroll"><table>' in rendered
    assert '<div class="equation"><code>E &lt; mc^2</code>' in rendered
    assert 'data-source-page="7"' in rendered
    assert "Original PDF · page 7" in rendered
    assert 'href="papers/example.pdf#page=7"' in rendered


def test_figure_fallback_and_debug_visibility() -> None:
    normal = render_mobile_article(_metadata(), _content())
    debug = render_mobile_article(_metadata(), _content(), debug=True)

    assert "Image unavailable in current extraction" in normal
    assert "Diagnostics" in debug
    assert "No warnings." in debug
    assert "Image unavailable in current extraction" in debug


def test_long_authors_and_many_references_remain_available() -> None:
    authors = tuple(f"Author {index}" for index in range(6))
    content = _content()
    refs = tuple(
        Reference(id=f"r-{index}", label=f"[{index}]", raw_text=f"Reference {index}")
        for index in range(120)
    )
    content = PaperContent(
        source_document_sha256=content.source_document_sha256,
        source_document_id=content.source_document_id,
        sections=content.sections,
        blocks=content.blocks,
        references=refs,
        citations=(),
        status=content.status,
    )
    rendered = render_mobile_article(
        _metadata(authors=authors), content, options=RenderOptions()
    )

    assert "et al." in rendered
    assert "Full author list" in rendered
    assert rendered.count('<li id="ref-') == 120
