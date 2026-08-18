"""Build a mobile presentation model from canonical paper data."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from paper_knowledge_base.content.models import (
    BlockType,
    ContentBlock,
    PaperContent,
    Paragraph,
    Section,
)
from paper_knowledge_base.content.quality.models import ContentQualityResult
from paper_knowledge_base.metadata.models import CanonicalPaperMetadata
from paper_knowledge_base.rendering.models import (
    ArticleHeader,
    ArticleNavigationItem,
    ArticleSection,
    AssetResolver,
    MobileArticle,
)


def build_mobile_article(
    metadata: CanonicalPaperMetadata | None,
    content_or_quality: PaperContent | ContentQualityResult,
    *,
    figure_resolver: AssetResolver | None = None,
    original_pdf_url: str | None = None,
    debug: bool = False,
    toc_max_depth: int = 2,
) -> MobileArticle:
    """Adapt cleaned canonical content into a renderer-owned view model."""

    content = (
        content_or_quality.content
        if isinstance(content_or_quality, ContentQualityResult)
        else content_or_quality
    )
    if toc_max_depth < 1:
        raise ValueError("toc_max_depth must be at least 1")

    header = _header(metadata, original_pdf_url=original_pdf_url)
    ordered_sections = tuple(
        sorted(content.sections, key=lambda item: (item.order, item.id))
    )
    blocks_by_section: dict[str, list[ContentBlock]] = {}
    for block in content.ordered_blocks:
        if block.section_id is not None:
            blocks_by_section.setdefault(block.section_id, []).append(block)

    abstract_section_ids = {
        section.id for section in ordered_sections if _is_abstract_section(section)
    }
    abstract_blocks: list[ContentBlock] = []
    seen_abstract_ids: set[str] = set()
    for section in ordered_sections:
        if section.id not in abstract_section_ids:
            continue
        for block in blocks_by_section.get(section.id, ()):
            if isinstance(block, Paragraph) and block.id not in seen_abstract_ids:
                abstract_blocks.append(block)
                seen_abstract_ids.add(block.id)
    for block in content.ordered_blocks:
        if (
            isinstance(block, Paragraph)
            and block.metadata_field == "scholarly.abstract"
            and block.id not in seen_abstract_ids
        ):
            abstract_blocks.append(block)
            seen_abstract_ids.add(block.id)

    section_by_id = {section.id: section for section in ordered_sections}
    depths = {
        section.id: _section_depth(section, section_by_id, set())
        for section in ordered_sections
    }
    anchors = _section_anchors(ordered_sections)
    article_sections = tuple(
        ArticleSection(
            section_id=section.id,
            anchor=anchors[section.id],
            title="" if section.special == "quality_hidden_heading" else section.title,
            html_level=min(depths[section.id] + 2, 6),
            depth=depths[section.id],
            blocks=tuple(blocks_by_section.get(section.id, ())),
        )
        for section in ordered_sections
        if section.id not in abstract_section_ids
    )
    navigation = _navigation(article_sections, toc_max_depth)
    known_section_ids = set(section_by_id)
    standalone = tuple(
        block
        for block in content.ordered_blocks
        if block.section_id not in known_section_ids
        and block.id not in seen_abstract_ids
    )
    diagnostics = (
        tuple(warning.message for warning in content_or_quality.warnings)
        if isinstance(content_or_quality, ContentQualityResult)
        else tuple(content.warnings)
    )

    return MobileArticle(
        header=header,
        sections=article_sections,
        navigation=navigation,
        abstract_blocks=tuple(abstract_blocks),
        standalone_blocks=standalone,
        references=content.references,
        citations=content.citations,
        source_document_id=content.source_document_id,
        source_document_sha256=content.source_document_sha256,
        diagnostics=diagnostics,
        figure_resolver=figure_resolver,
        debug=debug,
        toc_max_depth=toc_max_depth,
    )


def _header(
    metadata: CanonicalPaperMetadata | None,
    *,
    original_pdf_url: str | None,
) -> ArticleHeader:
    if metadata is None:
        return ArticleHeader(title="Untitled paper", original_pdf_url=original_pdf_url)
    return ArticleHeader(
        title=_value(metadata.title) or "Untitled paper",
        authors=tuple(
            author.display_name for author in metadata.authors if author.display_name
        ),
        venue=metadata.venue.name,
        publisher=metadata.venue.publisher,
        year=_value(metadata.year),
        doi=_value(metadata.doi),
        original_pdf_url=original_pdf_url,
    )


def _value(value: object) -> str | int | None:
    candidate = getattr(value, "value", value)
    return candidate if isinstance(candidate, (str, int)) else None


def _is_abstract_section(section: Section) -> bool:
    special = (section.special or "").casefold()
    return (
        special.startswith("derived_from_scholarly_metadata.abstract")
        or section.title.strip().casefold() == "abstract"
    )


def _section_depth(
    section: Section,
    section_by_id: dict[str, Section],
    visiting: set[str],
) -> int:
    if section.id in visiting or section.parent_id is None:
        return 0
    parent = section_by_id.get(section.parent_id)
    if parent is None:
        return 0
    visiting.add(section.id)
    return min(_section_depth(parent, section_by_id, visiting) + 1, 4)


def _section_anchors(sections: tuple[Section, ...]) -> dict[str, str]:
    anchors: dict[str, str] = {}
    used: set[str] = set()
    for section in sections:
        base = _slug(section.id) or _slug(section.title) or "section"
        anchor = f"section-{base}"
        if anchor in used:
            suffix = hashlib.sha1(f"{section.id}:{section.order}".encode()).hexdigest()[
                :8
            ]
            anchor = f"{anchor}-{suffix}"
        while anchor in used:
            anchor += "-x"
        anchors[section.id] = anchor
        used.add(anchor)
    return anchors


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug[:80]


@dataclass
class _NavigationNode:
    title: str
    anchor: str
    depth: int
    children: list[_NavigationNode]


def _navigation(
    sections: tuple[ArticleSection, ...],
    toc_max_depth: int,
) -> tuple[ArticleNavigationItem, ...]:
    roots: list[_NavigationNode] = []
    stack: list[_NavigationNode] = []
    for section in sections:
        if not section.title or section.depth >= toc_max_depth:
            continue
        node = _NavigationNode(section.title, section.anchor, section.depth, [])
        while stack and stack[-1].depth >= section.depth:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    def freeze(node: _NavigationNode) -> ArticleNavigationItem:
        return ArticleNavigationItem(
            title=node.title,
            anchor=node.anchor,
            depth=node.depth,
            children=tuple(freeze(child) for child in node.children),
        )

    return tuple(freeze(node) for node in roots)


def block_kind(block: ContentBlock) -> BlockType:
    """Expose the canonical block kind without leaking parser-specific types."""

    return block.block_type
