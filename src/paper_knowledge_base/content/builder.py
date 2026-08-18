"""Build canonical PaperContent from the existing processing result."""

from __future__ import annotations

from dataclasses import replace
from xml.etree import ElementTree

from paper_knowledge_base.content.docling_mapper import map_docling
from paper_knowledge_base.content.grobid_mapper import map_grobid
from paper_knowledge_base.content.models import (
    BlockType,
    ContentBlock,
    ContentFragment,
    ContentProvenance,
    ContentStatus,
    PaperContent,
    Paragraph,
    Reference,
    Section,
)
from paper_knowledge_base.content.normalization import (
    normalize_key,
    normalize_text,
    stable_id,
)
from paper_knowledge_base.processing.models import (
    PaperProcessingResult,
    ParserStatus,
)


def build_paper_content(
    processing_result: PaperProcessingResult,
    *,
    source_document_id: str | None = None,
) -> PaperContent:
    """Create canonical content while isolating missing or failed parsers.

    GROBID supplies the semantic section/reference/citation spine when available.
    Docling supplies layout-rich assets and OCR text when GROBID is absent.  When
    both succeed, Docling paragraphs are not duplicated; its figures, tables, and
    equations are attached to matching GROBID sections by normalized title.
    """

    warnings: list[str] = []
    grobid_fragment = _grobid_fragment(processing_result)
    docling_fragment = _docling_fragment(processing_result)
    if grobid_fragment is not None:
        warnings.extend(grobid_fragment.warnings)
    if docling_fragment is not None:
        warnings.extend(docling_fragment.warnings)

    grobid_available = bool(
        grobid_fragment and (grobid_fragment.sections or grobid_fragment.blocks)
    )
    docling_available = bool(
        docling_fragment and (docling_fragment.sections or docling_fragment.blocks)
    )
    if grobid_available:
        base = grobid_fragment
        sections = list(base.sections)
        references = list(base.references)
        citations = list(base.citations)
        if docling_fragment is not None:
            docling_types = {
                block.block_type
                for block in docling_fragment.blocks
                if block.block_type
                in {BlockType.FIGURE, BlockType.TABLE, BlockType.EQUATION}
            }
            blocks = [
                block for block in base.blocks if block.block_type not in docling_types
            ]
            blocks = _enrich_paragraph_locations(blocks, docling_fragment.blocks)
            blocks.extend(_supplement_with_docling(docling_fragment, sections))
        else:
            blocks = list(base.blocks)
    elif docling_available:
        base = docling_fragment
        blocks = list(base.blocks)
        sections = list(base.sections)
        references = []
        citations = []
    else:
        base = None
        blocks = []
        sections = []
        references = []
        citations = []

    if not references:
        references = _fallback_references(
            processing_result, parser_version=_version(processing_result, "grobid")
        )
    if not sections:
        sections, blocks = _fallback_scholarly_sections(processing_result)

    abstract = processing_result.scholarly.abstract.value
    if abstract:
        sections, blocks = _add_derived_abstract(
            sections,
            blocks,
            abstract,
            parser=processing_result.scholarly.abstract.source or "metadata",
            parser_version=_version(processing_result, "grobid"),
        )

    sections, blocks = _reorder_and_index(sections, blocks)
    citations = [
        citation
        for citation in citations
        if citation.block_id in {block.id for block in blocks}
    ]
    warnings.extend(_parser_warnings(processing_result))
    status = _status(processing_result, bool(blocks or references))
    if base is None and not blocks and not references:
        status = ContentStatus.FAILED

    return PaperContent(
        source_document_sha256=processing_result.file.sha256,
        source_document_id=source_document_id,
        sections=tuple(sections),
        blocks=tuple(blocks),
        references=tuple(references),
        citations=tuple(citations),
        status=status,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _grobid_fragment(result: PaperProcessingResult) -> ContentFragment | None:
    run = result.parser_runs.get("grobid")
    raw = run.raw_output if run and run.status == ParserStatus.SUCCESS else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return map_grobid(raw, parser_version=run.version if run else None)
    except (ElementTree.ParseError, ValueError, TypeError) as exc:
        return ContentFragment(
            parser="grobid",
            parser_version=run.version if run else None,
            warnings=(f"GROBID content mapping failed: {type(exc).__name__}.",),
        )


def _docling_fragment(result: PaperProcessingResult) -> ContentFragment | None:
    run = result.parser_runs.get("docling")
    raw = result.document.structured
    if run is None or run.status != ParserStatus.SUCCESS or not isinstance(raw, dict):
        return None
    try:
        return map_docling(raw, parser_version=run.version)
    except (ValueError, TypeError, KeyError) as exc:
        return ContentFragment(
            parser="docling",
            parser_version=run.version,
            warnings=(f"Docling content mapping failed: {type(exc).__name__}.",),
        )


def _supplement_with_docling(
    fragment: ContentFragment,
    grobid_sections: list[Section],
) -> list[ContentBlock]:
    preferred_types = {BlockType.FIGURE, BlockType.TABLE, BlockType.EQUATION}
    target_by_title = {
        normalize_key(section.title): section.id
        for section in grobid_sections
        if section.title
    }
    result: list[ContentBlock] = []
    for block in fragment.blocks:
        if block.block_type not in preferred_types:
            continue
        target = _matching_section(block, fragment.sections, target_by_title)
        result.append(replace(block, section_id=target))
    return result


def _enrich_paragraph_locations(
    grobid_blocks: list[ContentBlock],
    docling_blocks: tuple[ContentBlock, ...],
) -> list[ContentBlock]:
    """Attach Docling layout provenance only for conservative text overlaps."""

    docling_paragraphs = [
        block for block in docling_blocks if isinstance(block, Paragraph) and block.text
    ]
    enriched: list[ContentBlock] = []
    for block in grobid_blocks:
        if not isinstance(block, Paragraph) or block.source_location is not None:
            enriched.append(block)
            continue
        needle = normalize_key(block.text[:100])
        match = next(
            (
                candidate
                for candidate in docling_paragraphs
                if len(needle) >= 40 and needle in normalize_key(candidate.text)
            ),
            None,
        )
        if match is None:
            enriched.append(block)
            continue
        enriched.append(
            replace(
                block,
                source_location=match.source_location,
                provenance=(*block.provenance, *match.provenance),
            )
        )
    return enriched


def _matching_section(
    block: ContentBlock,
    source_sections: tuple[Section, ...],
    target_by_title: dict[str, str],
) -> str | None:
    if block.section_id is None:
        return None
    source = next(
        (section for section in source_sections if section.id == block.section_id), None
    )
    if source is None:
        return None
    return target_by_title.get(normalize_key(source.title))


def _fallback_scholarly_sections(
    result: PaperProcessingResult,
) -> tuple[list[Section], list[ContentBlock]]:
    sections: list[Section] = []
    blocks: list[ContentBlock] = []
    for index, source_section in enumerate(result.scholarly.sections, 1):
        section_id = stable_id("metadata-section", index)
        title = normalize_text(source_section.heading or "Body")
        sections.append(
            Section(
                id=section_id,
                title=title,
                label=None,
                level=1,
                order=index - 1,
                provenance=(ContentProvenance(parser=source_section.source),),
            )
        )
        values = [
            value
            for value in (source_section.text or "").split("\n\n")
            if normalize_text(value)
        ]
        for value_index, value in enumerate(values, 1):
            block_id = f"{section_id}-paragraph-{value_index:04d}"
            blocks.append(
                Paragraph(
                    id=block_id,
                    order=len(blocks) + 1,
                    section_id=section_id,
                    text=normalize_text(value),
                    provenance=(ContentProvenance(parser=source_section.source),),
                )
            )
        sections[-1] = replace(
            sections[-1],
            block_ids=tuple(
                block.id for block in blocks if block.section_id == section_id
            ),
        )
    return sections, blocks


def _fallback_references(
    result: PaperProcessingResult,
    *,
    parser_version: str | None,
) -> list[Reference]:
    return [
        Reference(
            id=stable_id("reference", index),
            label=str(index),
            raw_text=normalize_text(reference.text),
            provenance=(
                ContentProvenance(
                    parser=reference.source,
                    parser_version=parser_version,
                ),
            ),
        )
        for index, reference in enumerate(result.scholarly.references, 1)
        if normalize_text(reference.text)
    ]


def _add_derived_abstract(
    sections: list[Section],
    blocks: list[ContentBlock],
    abstract: str,
    *,
    parser: str,
    parser_version: str | None,
) -> tuple[list[Section], list[ContentBlock]]:
    section_id = "abstract-section"
    block_id = "abstract-block"
    abstract_section = Section(
        id=section_id,
        title="Abstract",
        label=None,
        level=1,
        order=0,
        block_ids=(block_id,),
        special="derived_from_scholarly_metadata.abstract",
        provenance=(ContentProvenance(parser=parser, parser_version=parser_version),),
    )
    abstract_block = Paragraph(
        id=block_id,
        order=0,
        section_id=section_id,
        text=normalize_text(abstract),
        metadata_field="scholarly.abstract",
        provenance=(ContentProvenance(parser=parser, parser_version=parser_version),),
    )
    return [abstract_section, *sections], [abstract_block, *blocks]


def _reorder_and_index(
    sections: list[Section],
    blocks: list[ContentBlock],
) -> tuple[list[Section], list[ContentBlock]]:
    blocks = [replace(block, order=index) for index, block in enumerate(blocks)]
    block_ids_by_section: dict[str, list[str]] = {}
    for block in blocks:
        if block.section_id is not None:
            block_ids_by_section.setdefault(block.section_id, []).append(block.id)
    sections = [
        replace(
            section,
            order=index,
            block_ids=tuple(block_ids_by_section.get(section.id, ())),
        )
        for index, section in enumerate(sections)
    ]
    return sections, blocks


def _parser_warnings(result: PaperProcessingResult) -> list[str]:
    warnings: list[str] = []
    for name, run in result.parser_runs.items():
        if run.status == ParserStatus.FAILED:
            detail = f": {run.error_message}" if run.error_message else ""
            warnings.append(f"{name} parser failed{detail}")
        elif run.status == ParserStatus.SKIPPED:
            warnings.append(f"{name} parser skipped")
    return warnings


def _status(result: PaperProcessingResult, has_content: bool) -> ContentStatus:
    if not has_content:
        return ContentStatus.FAILED
    runs = tuple(result.parser_runs.values())
    successful = [run for run in runs if run.status == ParserStatus.SUCCESS]
    failed = [run for run in runs if run.status == ParserStatus.FAILED]
    if failed and successful:
        return ContentStatus.PARTIAL
    return ContentStatus.COMPLETE


def _version(result: PaperProcessingResult, parser: str) -> str | None:
    run = result.parser_runs.get(parser)
    return run.version if run else None
