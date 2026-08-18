"""Render canonical PaperContent JSON as a small mobile-oriented debug page."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

CSS = """
:root { color-scheme: light; font-family: system-ui, sans-serif; }
body { margin: 0; background: #f4f5f7; color: #1d232a; }
article { box-sizing: border-box; max-width: 760px; margin: 0 auto; padding: 1rem; background: white; }
section { margin: 1.5rem 0; }
p { line-height: 1.65; }
figure { margin: 1rem 0; padding: .75rem; background: #f7f8fa; overflow-wrap: anywhere; }
figcaption { margin-top: .5rem; color: #56606b; }
table { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
th, td { border: 1px solid #c7cdd4; padding: .4rem; text-align: left; white-space: nowrap; }
.equation, .reference { padding: .6rem; background: #f7f8fa; }
@media (max-width: 480px) { article { padding: .75rem; } h1 { font-size: 1.4rem; } }
"""


def render_mobile_article(content: dict[str, Any]) -> str:
    """Render only the serialized canonical schema, never parser-native data."""

    sections = {item["id"]: item for item in content.get("sections", [])}
    blocks = {item["id"]: item for item in content.get("blocks", [])}
    citations = {item["id"]: item for item in content.get("citations", [])}
    references = {item["id"]: item for item in content.get("references", [])}
    by_section: dict[str, list[dict[str, Any]]] = {}
    for block in sorted(blocks.values(), key=lambda item: (item["order"], item["id"])):
        by_section.setdefault(block.get("section_id"), []).append(block)

    rendered_sections = []
    for section in sorted(
        sections.values(), key=lambda item: (item["order"], item["id"])
    ):
        heading = f"<h{min(int(section['level']) + 1, 6)}>{html.escape(section['title'])}</h{min(int(section['level']) + 1, 6)}>"
        body = "".join(
            _render_block(block, citations, references)
            for block in by_section.get(section["id"], [])
        )
        rendered_sections.append(
            f"<section id='{html.escape(section['id'])}'>{heading}{body}</section>"
        )
    known_section_ids = set(sections)
    standalone = "".join(
        _render_block(block, citations, references)
        for block in sorted(
            blocks.values(), key=lambda item: (item["order"], item["id"])
        )
        if block.get("section_id") not in known_section_ids
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
        "content='width=device-width, initial-scale=1'><title>Paper content debug</title>"
        f"<style>{CSS}</style></head><body><article>"
        + "".join(rendered_sections)
        + standalone
        + _render_references(content.get("references", []))
        + "</article></body></html>"
    )


def _render_block(
    block: dict[str, Any],
    citations: dict[str, dict[str, Any]],
    references: dict[str, dict[str, Any]],
) -> str:
    kind = block.get("block_type")
    if kind == "paragraph":
        raw_text = block.get("text", "")
        spans = []
        for citation_id in block.get("citation_ids", []):
            citation = citations.get(citation_id)
            if not citation:
                continue
            start = citation.get("start")
            end = citation.get("end")
            target = next(iter(citation.get("reference_ids", ())), None)
            if (
                isinstance(start, int)
                and isinstance(end, int)
                and 0 <= start < end <= len(raw_text)
                and target in references
                and raw_text[start:end] == citation.get("display")
            ):
                spans.append((start, end, target))
        pieces = []
        cursor = 0
        for start, end, target in sorted(spans):
            if start < cursor:
                continue
            pieces.append(html.escape(raw_text[cursor:start]))
            display = html.escape(raw_text[start:end])
            pieces.append(f"<a href='#ref-{html.escape(target)}'>{display}</a>")
            cursor = end
        pieces.append(html.escape(raw_text[cursor:]))
        return f"<p>{''.join(pieces)}</p>"
    if kind == "figure":
        caption = html.escape(block.get("caption") or "")
        label = html.escape(block.get("label") or "Figure")
        return f"<figure><strong>{label}</strong><figcaption>{caption}</figcaption></figure>"
    if kind == "table":
        headers = block.get("headers", [])
        rows = block.get("rows", [])
        head = (
            "<thead><tr>"
            + "".join(f"<th>{html.escape(str(value))}</th>" for value in headers)
            + "</tr></thead>"
            if headers
            else ""
        )
        body = (
            "<tbody>"
            + "".join(
                "<tr>"
                + "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
                + "</tr>"
                for row in rows
            )
            + "</tbody>"
        )
        return f"<figure><strong>{html.escape(block.get('label') or 'Table')}</strong><table>{head}{body}</table><figcaption>{html.escape(block.get('caption') or '')}</figcaption></figure>"
    if kind == "equation":
        return f"<p class='equation'>{html.escape(block.get('latex') or block.get('text') or '')}</p>"
    return ""


def _render_references(references: list[dict[str, Any]]) -> str:
    if not references:
        return ""
    items = []
    for reference in references:
        reference_id = html.escape(reference["id"])
        label = html.escape(reference.get("label") or "")
        items.append(
            f"<li id='ref-{reference_id}'><strong>{label}</strong> {html.escape(reference.get('raw_text', ''))}</li>"
        )
    return "<section><h2>References</h2><ol>" + "".join(items) + "</ol></section>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="PaperContent JSON")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    content = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.write_text(render_mobile_article(content), encoding="utf-8")


if __name__ == "__main__":
    main()
