"""Translate the observed Docling JSON shape into canonical content types."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from paper_knowledge_base.content.models import (
    BoundingBox,
    ContentFragment,
    ContentProvenance,
    Equation,
    Figure,
    Paragraph,
    Section,
    SourceLocation,
    Table,
)
from paper_knowledge_base.content.normalization import (
    normalize_text,
    split_heading,
    stable_id,
)

NOISE_LABELS = frozenset({"page_header", "page_footer", "footnote", "furniture"})


def map_docling(
    raw_document: dict[str, Any],
    *,
    parser_version: str | None = None,
) -> ContentFragment:
    """Map Docling's declared order and layout metadata without exposing its schema."""

    texts = {
        _ref_key(item.get("self_ref"), f"#/texts/{index}"): item
        for index, item in enumerate(raw_document.get("texts", []))
        if isinstance(item, dict)
    }
    pictures = {
        _ref_key(item.get("self_ref"), f"#/pictures/{index}"): item
        for index, item in enumerate(raw_document.get("pictures", []))
        if isinstance(item, dict)
    }
    tables = {
        _ref_key(item.get("self_ref"), f"#/tables/{index}"): item
        for index, item in enumerate(raw_document.get("tables", []))
        if isinstance(item, dict)
    }
    consumed_caption_refs: set[str] = set()
    for item in (*pictures.values(), *tables.values()):
        for caption in item.get("captions", ()):
            if isinstance(caption, dict) and caption.get("$ref"):
                consumed_caption_refs.add(_ref_key(caption["$ref"], ""))

    sections: list[Section] = []
    blocks: list[Paragraph | Figure | Table | Equation] = []
    section_blocks: dict[str, list[str]] = {}
    warnings: list[str] = []
    section_stack: list[tuple[int, str]] = []
    next_block = 0

    def add_section(item: dict[str, Any]) -> str:
        raw_title = normalize_text(item.get("text", ""))
        label, title = split_heading(raw_title)
        level = _heading_level(raw_title, sections, section_stack)
        while section_stack and section_stack[-1][0] >= level:
            section_stack.pop()
        parent_id = section_stack[-1][1] if section_stack else None
        section_id = stable_id("docling-section", len(sections) + 1)
        sections.append(
            Section(
                id=section_id,
                title=title,
                label=label,
                level=level,
                order=len(sections),
                parent_id=parent_id,
                provenance=(_provenance(item, parser_version),),
            )
        )
        section_blocks[section_id] = []
        section_stack.append((level, section_id))
        return section_id

    current_section: str | None = None

    def add_block(block: Paragraph | Figure | Table | Equation) -> None:
        blocks.append(block)
        if block.section_id is not None:
            section_blocks.setdefault(block.section_id, []).append(block.id)

    def next_id() -> tuple[str, int]:
        nonlocal next_block
        next_block += 1
        return stable_id("docling-block", next_block), next_block

    ordered_refs = _body_refs(raw_document)
    seen_assets: set[str] = set()
    for ref in ordered_refs:
        if ref in texts:
            item = texts[ref]
            label = item.get("label")
            if label == "section_header":
                current_section = add_section(item)
                continue
            if label in NOISE_LABELS or ref in consumed_caption_refs:
                continue
            text = normalize_text(item.get("text", ""))
            if not text or label == "caption":
                continue
            block_id, order = next_id()
            provenance = (_provenance(item, parser_version),)
            if label == "formula":
                add_block(
                    Equation(
                        id=block_id,
                        order=order,
                        section_id=current_section,
                        text=text,
                        source_location=_source_location(item, "docling"),
                        provenance=provenance,
                    )
                )
            else:
                add_block(
                    Paragraph(
                        id=block_id,
                        order=order,
                        section_id=current_section,
                        text=text,
                        source_location=_source_location(item, "docling"),
                        provenance=provenance,
                    )
                )
        elif ref in pictures:
            seen_assets.add(ref)
            item = pictures[ref]
            block_id, order = next_id()
            add_block(
                Figure(
                    id=block_id,
                    order=order,
                    section_id=current_section,
                    label=_text_value(item.get("label")),
                    caption=_caption_text(item, texts),
                    asset_ref=_asset_ref(item, ref),
                    source_location=_source_location(item, "docling"),
                    provenance=(_provenance(item, parser_version),),
                )
            )
        elif ref in tables:
            seen_assets.add(ref)
            item = tables[ref]
            block_id, order = next_id()
            headers, rows = _table_grid(item)
            add_block(
                Table(
                    id=block_id,
                    order=order,
                    section_id=current_section,
                    label=_text_value(item.get("label")),
                    caption=_caption_text(item, texts),
                    headers=headers,
                    rows=rows,
                    plain_text=_table_plain_text(headers, rows),
                    source_location=_source_location(item, "docling"),
                    provenance=(_provenance(item, parser_version),),
                )
            )

    for ref, item in (*pictures.items(), *tables.items()):
        if ref in seen_assets:
            continue
        block_id, order = next_id()
        if ref in pictures:
            add_block(
                Figure(
                    id=block_id,
                    order=order,
                    section_id=None,
                    label=_text_value(item.get("label")),
                    caption=_caption_text(item, texts),
                    asset_ref=_asset_ref(item, ref),
                    source_location=_source_location(item, "docling"),
                    provenance=(_provenance(item, parser_version),),
                )
            )
        else:
            headers, rows = _table_grid(item)
            add_block(
                Table(
                    id=block_id,
                    order=order,
                    section_id=None,
                    label=_text_value(item.get("label")),
                    caption=_caption_text(item, texts),
                    headers=headers,
                    rows=rows,
                    plain_text=_table_plain_text(headers, rows),
                    source_location=_source_location(item, "docling"),
                    provenance=(_provenance(item, parser_version),),
                )
            )

    sections = [
        replace(section, block_ids=tuple(section_blocks.get(section.id, ())))
        for section in sections
    ]
    if not blocks:
        warnings.append("Docling produced no canonical content blocks.")
    return ContentFragment(
        parser="docling",
        parser_version=parser_version,
        sections=tuple(sections),
        blocks=tuple(blocks),
        warnings=tuple(warnings),
    )


def _body_refs(document: dict[str, Any]) -> list[str]:
    body = document.get("body")
    if not isinstance(body, dict):
        return []
    return [
        _ref_key(item.get("$ref"), "")
        for item in body.get("children", ())
        if isinstance(item, dict) and item.get("$ref")
    ]


def _ref_key(value: object, fallback: str) -> str:
    return str(value or fallback)


def _heading_level(
    text: str,
    sections: list[Section],
    stack: list[tuple[int, str]],
) -> int:
    match = re.match(r"^(\d+(?:\.\d+)*)\b", text)
    if match:
        return match.group(1).count(".") + 1
    if not stack:
        return 1
    return max(1, stack[-1][0])


def _provenance(item: dict[str, Any], parser_version: str | None) -> ContentProvenance:
    return ContentProvenance(
        parser="docling",
        parser_version=parser_version,
        source_element_id=item.get("self_ref"),
    )


def _source_location(item: dict[str, Any], parser: str) -> SourceLocation | None:
    provenance = item.get("prov")
    if not isinstance(provenance, list) or not provenance:
        return None
    first = provenance[0]
    if not isinstance(first, dict):
        return None
    bbox = first.get("bbox")
    location_bbox = None
    coordinate_origin = None
    if isinstance(bbox, dict):
        try:
            coordinate_origin = (
                str(bbox.get("coord_origin")) if bbox.get("coord_origin") else None
            )
            location_bbox = BoundingBox(
                x0=float(bbox["l"]),
                y0=float(bbox["t"]),
                x1=float(bbox["r"]),
                y1=float(bbox["b"]),
                coordinate_origin=coordinate_origin,
            )
        except (KeyError, TypeError, ValueError):
            location_bbox = None
    page = first.get("page_no")
    return SourceLocation(
        page_number=int(page) if isinstance(page, (int, float)) else None,
        bbox=location_bbox,
        parser=parser,
        source_element_id=item.get("self_ref"),
        coordinate_system=f"docling-{coordinate_origin}"
        if coordinate_origin
        else "docling-raw",
    )


def _caption_text(item: dict[str, Any], texts: dict[str, dict[str, Any]]) -> str | None:
    values: list[str] = []
    for caption in item.get("captions", ()):
        if not isinstance(caption, dict):
            continue
        ref = _ref_key(caption.get("$ref"), "")
        text = texts.get(ref, {}).get("text")
        if text:
            values.append(normalize_text(text))
    return " ".join(values) or None


def _asset_ref(item: dict[str, Any], ref: str) -> str | None:
    image = item.get("image")
    uri = image.get("uri") if isinstance(image, dict) else None
    if not uri:
        return None
    if str(uri).startswith("data:"):
        return f"docling:{ref}"
    return str(uri)


def _table_grid(
    item: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    cells = item.get("data", {}).get("table_cells", [])
    if not isinstance(cells, list):
        return (), ()
    headers: dict[int, str] = {}
    rows: dict[int, dict[int, str]] = {}
    for cell in cells:
        if not isinstance(cell, dict) or not cell.get("text"):
            continue
        row = int(cell.get("start_row_offset_idx", 0))
        col = int(cell.get("start_col_offset_idx", 0))
        text = normalize_text(cell["text"])
        if cell.get("column_header") and row == 0:
            headers[col] = text
        else:
            rows.setdefault(row, {})[col] = text
    width = (
        max(
            [*headers.keys(), *(col for row in rows.values() for col in row)],
            default=-1,
        )
        + 1
    )
    header_values = (
        tuple(headers.get(index, "") for index in range(width)) if headers else ()
    )
    row_values = tuple(
        tuple(row.get(index, "") for index in range(width))
        for _, row in sorted(rows.items())
    )
    return header_values, row_values


def _table_plain_text(
    headers: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> str | None:
    values = [" | ".join(headers)] if headers else []
    values.extend(" | ".join(row) for row in rows)
    return "\n".join(values) or None


def _text_value(value: object) -> str | None:
    return normalize_text(value) if value else None
