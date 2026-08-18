"""Compatibility CLI for rendering serialized canonical PaperContent."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from paper_knowledge_base.content import (
    BlockType,
    BoundingBox,
    Citation,
    ContentProvenance,
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
from paper_knowledge_base.rendering import render_mobile_article as _render_models


def render_mobile_article(
    content: PaperContent | Mapping[str, Any],
    *,
    metadata=None,
    debug: bool = False,
    original_pdf_url: str | None = None,
) -> str:
    """Render canonical content, retaining the original serialized-dict API."""

    canonical = (
        content
        if isinstance(content, PaperContent)
        else paper_content_from_dict(content)
    )
    return _render_models(
        metadata,
        canonical,
        debug=debug,
        original_pdf_url=original_pdf_url,
    )


def paper_content_from_dict(payload: Mapping[str, Any]) -> PaperContent:
    """Rehydrate the project's own deterministic JSON shape for the CLI shim."""

    return PaperContent(
        source_document_sha256=payload.get("source_document_sha256"),
        source_document_id=payload.get("source_document_id"),
        sections=tuple(_section(item) for item in payload.get("sections", ())),
        blocks=tuple(_block(item) for item in payload.get("blocks", ())),
        references=tuple(_reference(item) for item in payload.get("references", ())),
        citations=tuple(_citation(item) for item in payload.get("citations", ())),
        status=ContentStatus(payload.get("status", ContentStatus.FAILED.value)),
        warnings=tuple(str(item) for item in payload.get("warnings", ())),
        schema_version=int(payload.get("schema_version", 1)),
    )


def _section(item: Mapping[str, Any]) -> Section:
    return Section(
        id=str(item["id"]),
        title=str(item.get("title", "")),
        label=item.get("label"),
        level=int(item.get("level", 0)),
        order=int(item.get("order", 0)),
        parent_id=item.get("parent_id"),
        block_ids=tuple(item.get("block_ids", ())),
        provenance=tuple(_provenance(value) for value in item.get("provenance", ())),
        special=item.get("special"),
    )


def _block(item: Mapping[str, Any]):
    common = {
        "id": str(item["id"]),
        "order": int(item.get("order", 0)),
        "section_id": item.get("section_id"),
        "source_location": _location(item.get("source_location")),
        "provenance": tuple(_provenance(value) for value in item.get("provenance", ())),
    }
    kind = item.get("block_type", BlockType.PARAGRAPH.value)
    if kind == BlockType.PARAGRAPH.value:
        return Paragraph(
            **common,
            text=str(item.get("text", "")),
            citation_ids=tuple(item.get("citation_ids", ())),
            metadata_field=item.get("metadata_field"),
        )
    if kind == BlockType.FIGURE.value:
        return Figure(
            **common,
            label=item.get("label"),
            caption=item.get("caption"),
            asset_ref=item.get("asset_ref"),
        )
    if kind == BlockType.TABLE.value:
        return Table(
            **common,
            label=item.get("label"),
            caption=item.get("caption"),
            headers=tuple(str(value) for value in item.get("headers", ())),
            rows=tuple(
                tuple(str(value) for value in row) for row in item.get("rows", ())
            ),
            plain_text=item.get("plain_text"),
        )
    if kind == BlockType.EQUATION.value:
        return Equation(**common, text=item.get("text"), latex=item.get("latex"))
    raise ValueError(f"unsupported canonical block type: {kind}")


def _location(item: Mapping[str, Any] | None) -> SourceLocation | None:
    if item is None:
        return None
    box = item.get("bbox")
    bbox = (
        BoundingBox(
            x0=float(box["x0"]),
            y0=float(box["y0"]),
            x1=float(box["x1"]),
            y1=float(box["y1"]),
            coordinate_origin=box.get("coordinate_origin"),
        )
        if box
        else None
    )
    return SourceLocation(
        page_number=item.get("page_number"),
        bbox=bbox,
        parser=item.get("parser"),
        source_element_id=item.get("source_element_id"),
        coordinate_system=item.get("coordinate_system"),
        raw_coordinates=item.get("raw_coordinates"),
    )


def _provenance(item: Mapping[str, Any]) -> ContentProvenance:
    return ContentProvenance(
        parser=str(item.get("parser", "unknown")),
        source_element_id=item.get("source_element_id"),
        parser_version=item.get("parser_version"),
        note=item.get("note"),
    )


def _citation(item: Mapping[str, Any]) -> Citation:
    return Citation(
        id=str(item["id"]),
        display=str(item.get("display", "")),
        reference_ids=tuple(item.get("reference_ids", ())),
        block_id=item.get("block_id"),
        start=item.get("start"),
        end=item.get("end"),
        provenance=tuple(_provenance(value) for value in item.get("provenance", ())),
    )


def _reference(item: Mapping[str, Any]) -> Reference:
    return Reference(
        id=str(item["id"]),
        label=item.get("label"),
        raw_text=str(item.get("raw_text", "")),
        title=item.get("title"),
        authors=tuple(str(value) for value in item.get("authors", ())),
        year=item.get("year"),
        venue=item.get("venue"),
        doi=item.get("doi"),
        identifiers={
            str(key): str(value) for key, value in item.get("identifiers", {}).items()
        },
        provenance=tuple(_provenance(value) for value in item.get("provenance", ())),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Canonical PaperContent JSON")
    parser.add_argument("output", type=Path)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--original-pdf-url")
    args = parser.parse_args()
    content = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_mobile_article(
            content,
            debug=args.debug,
            original_pdf_url=args.original_pdf_url,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
