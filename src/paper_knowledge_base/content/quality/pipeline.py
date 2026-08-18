"""Public entry points for conservative canonical-content quality processing."""

from __future__ import annotations

from dataclasses import replace

from paper_knowledge_base.content.models import (
    Citation,
    ContentBlock,
    PaperContent,
    Section,
)
from paper_knowledge_base.content.quality.blocks import clean_blocks
from paper_knowledge_base.content.quality.diagnostics import diagnose_content
from paper_knowledge_base.content.quality.figures import clean_figures
from paper_knowledge_base.content.quality.models import (
    ContentQualityMetrics,
    ContentQualityResult,
    ContentTransformation,
    ContentWarning,
    TransformationAction,
    citation_is_valid,
)
from paper_knowledge_base.content.quality.sections import clean_sections


def improve_content_quality(content: PaperContent) -> ContentQualityResult:
    """Return a cleaned copy while preserving the original canonical content.

    The pipeline is intentionally parser-independent and deterministic.  It only
    changes section presentation or suppresses content when structural evidence
    is strong enough; uncertain figures remain in the cleaned copy with warnings.
    """

    sections, blocks, section_warnings, section_transformations = clean_sections(
        content
    )
    interim = _with_structure(content, sections, blocks)

    blocks, block_warnings, block_transformations = clean_blocks(interim)
    interim = _with_structure(content, sections, blocks)

    (
        blocks,
        figure_warnings,
        figure_transformations,
        figure_assessments,
        caption_associations,
    ) = clean_figures(interim)
    cleaned = _with_structure(content, sections, blocks)

    diagnostic_warnings = diagnose_content(cleaned)
    warnings = _deduplicate_warnings(
        (*section_warnings, *block_warnings, *figure_warnings, *diagnostic_warnings)
    )
    transformations = _deduplicate_transformations(
        (*section_transformations, *block_transformations, *figure_transformations)
    )
    metrics = _metrics(content, cleaned, warnings, transformations)
    return ContentQualityResult(
        source_content=content,
        content=cleaned,
        warnings=warnings,
        transformations=transformations,
        metrics=metrics,
        figure_assessments=figure_assessments,
        caption_associations=caption_associations,
    )


def normalize_paper_content(content: PaperContent) -> ContentQualityResult:
    """Compatibility alias for callers that describe quality processing as normalization."""

    return improve_content_quality(content)


def _with_structure(
    source: PaperContent,
    sections: tuple[Section, ...],
    blocks: tuple[ContentBlock, ...],
) -> PaperContent:
    block_ids_by_section: dict[str, list[str]] = {}
    for block in blocks:
        if block.section_id is not None:
            block_ids_by_section.setdefault(block.section_id, []).append(block.id)
    rebuilt_sections = tuple(
        replace(
            section,
            block_ids=tuple(block_ids_by_section.get(section.id, ())),
        )
        for section in sections
    )
    return replace(source, sections=rebuilt_sections, blocks=blocks)


def _deduplicate_warnings(
    warnings: tuple[ContentWarning, ...],
) -> tuple[ContentWarning, ...]:
    seen: set[tuple[object, ...]] = set()
    result: list[ContentWarning] = []
    for warning in warnings:
        key = (
            warning.code,
            warning.severity,
            warning.message,
            warning.block_id,
            warning.section_id,
            warning.figure_id,
        )
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return tuple(result)


def _deduplicate_transformations(
    transformations: tuple[ContentTransformation, ...],
) -> tuple[ContentTransformation, ...]:
    seen: set[tuple[object, ...]] = set()
    result: list[ContentTransformation] = []
    for transformation in transformations:
        key = (
            transformation.action,
            transformation.target_id,
            transformation.source_ids,
        )
        if key not in seen:
            seen.add(key)
            result.append(transformation)
    return tuple(result)


def _metrics(
    source: PaperContent,
    cleaned: PaperContent,
    warnings: tuple[ContentWarning, ...],
    transformations: tuple[ContentTransformation, ...],
) -> ContentQualityMetrics:
    source_blocks = {block.id: block for block in source.blocks}
    suppressed_pictures = sum(
        transformation.action == TransformationAction.SUPPRESS_PICTURE
        for transformation in transformations
    )
    duplicate_paragraphs = sum(
        transformation.action == TransformationAction.SUPPRESS_DUPLICATE_BLOCK
        and getattr(source_blocks.get(transformation.target_id), "text", None)
        is not None
        for transformation in transformations
    )
    section_noise_actions = {
        TransformationAction.REMOVE_EMPTY_SECTION,
        TransformationAction.HIDE_SECTION_HEADING,
        TransformationAction.MERGE_DUPLICATE_SECTION,
    }
    section_noise = sum(
        transformation.action in section_noise_actions
        for transformation in transformations
    )
    header_footer = sum(
        transformation.action == TransformationAction.SUPPRESS_REPEATED_PAGE_NOISE
        for transformation in transformations
    )
    citations_resolved = sum(
        _citation_resolves(citation, cleaned) for citation in cleaned.citations
    )
    citation_rate = (
        citations_resolved / len(cleaned.citations) if cleaned.citations else 1.0
    )
    located_blocks = sum(block.source_location is not None for block in cleaned.blocks)
    location_coverage = located_blocks / len(cleaned.blocks) if cleaned.blocks else 0.0
    return ContentQualityMetrics(
        raw_section_count=len(source.sections),
        clean_section_count=len(cleaned.sections),
        raw_block_count=len(source.blocks),
        clean_block_count=len(cleaned.blocks),
        raw_figure_count=sum(
            block.block_type.value == "figure" for block in source.blocks
        ),
        clean_figure_count=sum(
            block.block_type.value == "figure" for block in cleaned.blocks
        ),
        removed_section_noise_count=section_noise,
        suppressed_picture_count=suppressed_pictures,
        duplicate_paragraph_count=duplicate_paragraphs,
        header_footer_removed_count=header_footer,
        warning_count=len(warnings),
        citation_resolution_rate=citation_rate,
        source_location_coverage=location_coverage,
    )


def _citation_resolves(citation: Citation, content: PaperContent) -> bool:
    block_id = citation.block_id
    block = content.blocks_by_id.get(block_id)
    if (
        block is None
        or not citation.reference_ids
        or not citation_is_valid(citation, content)
    ):
        return False
    start = citation.start
    end = citation.end
    display = citation.display
    if start is None and end is None:
        return True
    text = getattr(block, "text", None)
    return (
        isinstance(text, str)
        and isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start < end <= len(text)
        and text[start:end] == display
    )
