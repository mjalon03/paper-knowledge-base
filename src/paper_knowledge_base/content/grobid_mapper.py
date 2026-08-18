"""Translate GROBID TEI into canonical content types."""

from __future__ import annotations

import re
from dataclasses import replace
from xml.etree import ElementTree

from paper_knowledge_base.content.models import (
    BoundingBox,
    Citation,
    ContentFragment,
    ContentProvenance,
    Equation,
    Figure,
    Paragraph,
    Reference,
    Section,
    SourceLocation,
    Table,
)
from paper_knowledge_base.content.normalization import (
    find_reliable_span,
    normalize_text,
    split_heading,
    stable_id,
)

TEI = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def map_grobid(
    raw_tei_xml: str,
    *,
    parser_version: str | None = None,
) -> ContentFragment:
    """Map explicit TEI semantics while preserving GROBID coordinates as-is."""

    root = ElementTree.fromstring(raw_tei_xml)
    references, reference_by_source_id = _references(root, parser_version)
    sections: list[Section] = []
    blocks: list[Paragraph | Figure | Table | Equation] = []
    citations: list[Citation] = []
    section_blocks: dict[str, list[str]] = {}
    counters = {"section": 0, "block": 0, "citation": 0}

    body = root.find(".//tei:text/tei:body", TEI)

    def new_section(
        element: ElementTree.Element, parent_id: str | None, depth: int
    ) -> str:
        counters["section"] += 1
        raw_heading = _element_text(element.find("tei:head", TEI))
        label, title = split_heading(raw_heading) if raw_heading else (None, "Body")
        section_id = stable_id("grobid-section", counters["section"])
        sections.append(
            Section(
                id=section_id,
                title=title,
                label=label,
                level=max(depth, 1),
                order=len(sections),
                parent_id=parent_id,
                provenance=(
                    ContentProvenance(
                        parser="grobid",
                        parser_version=parser_version,
                        source_element_id=element.get(XML_ID),
                    ),
                ),
            )
        )
        section_blocks[section_id] = []
        return section_id

    def add_block(block: Paragraph | Figure | Table | Equation) -> None:
        blocks.append(block)
        if block.section_id is not None:
            section_blocks.setdefault(block.section_id, []).append(block.id)

    def walk_division(
        division: ElementTree.Element,
        parent_id: str | None,
        depth: int,
    ) -> None:
        section_id = new_section(division, parent_id, depth)
        for child in list(division):
            if _local_name(child.tag) == "p":
                add_block(
                    _paragraph(
                        child,
                        section_id,
                        counters,
                        citations,
                        reference_by_source_id,
                        parser_version,
                    )
                )
            elif _local_name(child.tag) == "figure":
                add_block(_figure_or_table(child, section_id, counters, parser_version))
            elif _local_name(child.tag) == "formula":
                add_block(_equation(child, section_id, counters, parser_version))
            elif _local_name(child.tag) == "div":
                walk_division(child, section_id, depth + 1)

    if body is not None:
        for child in list(body):
            name = _local_name(child.tag)
            if name == "div":
                walk_division(child, None, 1)
            elif name == "p":
                if not sections:
                    implicit = ElementTree.Element("div")
                    section_id = new_section(implicit, None, 1)
                else:
                    section_id = sections[-1].id
                add_block(
                    _paragraph(
                        child,
                        section_id,
                        counters,
                        citations,
                        reference_by_source_id,
                        parser_version,
                    )
                )
            elif name == "figure":
                section_id = sections[-1].id if sections else None
                add_block(_figure_or_table(child, section_id, counters, parser_version))
            elif name == "formula":
                section_id = sections[-1].id if sections else None
                add_block(_equation(child, section_id, counters, parser_version))

    sections = [
        replace(section, block_ids=tuple(section_blocks.get(section.id, ())))
        for section in sections
    ]
    return ContentFragment(
        parser="grobid",
        parser_version=parser_version,
        sections=tuple(sections),
        blocks=tuple(blocks),
        references=tuple(references),
        citations=tuple(citations),
    )


def _paragraph(
    element: ElementTree.Element,
    section_id: str,
    counters: dict[str, int],
    citations: list[Citation],
    reference_by_source_id: dict[str, str],
    parser_version: str | None,
) -> Paragraph:
    text = _element_text(element)
    counters["block"] += 1
    block_id = stable_id("grobid-block", counters["block"])
    citation_ids: list[str] = []
    cursor = 0
    for ref in element.findall(".//tei:ref[@type='bibr']", TEI):
        display = _element_text(ref)
        if not display:
            continue
        counters["citation"] += 1
        citation_id = stable_id("citation", counters["citation"])
        target_ids = tuple(
            reference_by_source_id[target.lstrip("#")]
            for target in (ref.get("target") or "").split()
            if target.lstrip("#") in reference_by_source_id
        )
        span = find_reliable_span(text, display, cursor=cursor)
        if span is not None:
            cursor = span[1]
        citations.append(
            Citation(
                id=citation_id,
                display=display,
                reference_ids=target_ids,
                block_id=block_id,
                start=span[0] if span else None,
                end=span[1] if span else None,
                provenance=(
                    ContentProvenance(
                        parser="grobid",
                        parser_version=parser_version,
                        source_element_id=ref.get(XML_ID),
                    ),
                ),
            )
        )
        citation_ids.append(citation_id)
    return Paragraph(
        id=block_id,
        order=counters["block"],
        section_id=section_id,
        text=text,
        citation_ids=tuple(citation_ids),
        source_location=_source_location(element, parser="grobid"),
        provenance=(
            ContentProvenance(
                parser="grobid",
                parser_version=parser_version,
                source_element_id=element.get(XML_ID),
            ),
        ),
    )


def _figure_or_table(
    element: ElementTree.Element,
    section_id: str | None,
    counters: dict[str, int],
    parser_version: str | None,
) -> Figure | Table:
    counters["block"] += 1
    block_id = stable_id("grobid-block", counters["block"])
    label = _element_text(element.find("tei:label", TEI))
    caption = _element_text(element.find("tei:figDesc", TEI))
    provenance = (
        ContentProvenance(
            parser="grobid",
            parser_version=parser_version,
            source_element_id=element.get(XML_ID),
        ),
    )
    common = {
        "id": block_id,
        "order": counters["block"],
        "section_id": section_id,
        "source_location": _source_location(element, parser="grobid"),
        "provenance": provenance,
        "label": label,
        "caption": caption,
    }
    if element.get("type") == "table":
        return Table(
            **common,
            plain_text=_element_text(element.find(".//tei:table", TEI))
            or _element_text(element),
        )
    graphic = element.find(".//tei:graphic", TEI)
    return Figure(
        **common, asset_ref=graphic.get("url") if graphic is not None else None
    )


def _equation(
    element: ElementTree.Element,
    section_id: str | None,
    counters: dict[str, int],
    parser_version: str | None,
) -> Equation:
    counters["block"] += 1
    return Equation(
        id=stable_id("grobid-block", counters["block"]),
        order=counters["block"],
        section_id=section_id,
        text=_element_text(element),
        latex=element.get("notation") or None,
        source_location=_source_location(element, parser="grobid"),
        provenance=(
            ContentProvenance(
                parser="grobid",
                parser_version=parser_version,
                source_element_id=element.get(XML_ID),
            ),
        ),
    )


def _references(
    root: ElementTree.Element,
    parser_version: str | None,
) -> tuple[list[Reference], dict[str, str]]:
    result: list[Reference] = []
    source_ids: dict[str, str] = {}
    for index, element in enumerate(
        root.findall(".//tei:listBibl/tei:biblStruct", TEI), 1
    ):
        source_id = element.get(XML_ID) or f"index-{index}"
        reference_id = stable_id("reference", index)
        source_ids[source_id] = reference_id
        title = _element_text(element.find(".//tei:analytic/tei:title", TEI))
        if title is None:
            title = _element_text(element.find(".//tei:monogr/tei:title", TEI))
        authors = tuple(
            text
            for text in (
                _element_text(node)
                for node in element.findall(
                    ".//tei:analytic/tei:author/tei:persName", TEI
                )
            )
            if text
        )
        year_text = _element_text(element.find(".//tei:date", TEI))
        year_match = re.search(r"\b(19|20)\d{2}\b", year_text or "")
        doi = _element_text(element.find(".//tei:idno[@type='DOI']", TEI))
        result.append(
            Reference(
                id=reference_id,
                label=_element_text(element.find("tei:label", TEI)) or str(index),
                raw_text=_element_text(element) or "",
                title=title,
                authors=authors,
                year=int(year_match.group(0)) if year_match else None,
                venue=_element_text(element.find(".//tei:monogr/tei:title", TEI)),
                doi=doi,
                identifiers={"grobid_xml_id": source_id},
                provenance=(
                    ContentProvenance(
                        parser="grobid",
                        parser_version=parser_version,
                        source_element_id=source_id,
                    ),
                ),
            )
        )
    return result, source_ids


def _source_location(
    element: ElementTree.Element,
    *,
    parser: str,
) -> SourceLocation | None:
    raw = element.get("coords")
    if not raw:
        return None
    parts = raw.split(",")
    try:
        page, x, y, width, height = (float(part) for part in parts[:5])
    except (TypeError, ValueError):
        return SourceLocation(
            parser=parser,
            source_element_id=element.get(XML_ID),
            coordinate_system="grobid-raw",
            raw_coordinates=raw,
        )
    return SourceLocation(
        page_number=int(page),
        bbox=BoundingBox(
            x0=x,
            y0=y,
            x1=x + width,
            y1=y + height,
            coordinate_origin="GROBID_PDF",
        ),
        parser=parser,
        source_element_id=element.get(XML_ID),
        coordinate_system="grobid-pdf-x-y-width-height",
        raw_coordinates=raw,
    )


def _element_text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return normalize_text(" ".join(element.itertext()))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
