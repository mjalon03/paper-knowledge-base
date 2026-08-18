from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from benchmark.adapters.models import NormalizedResult
from paper_knowledge_base.parsers.tei import (
    TEI,
    element_text,
    extract_tei_fields,
    unique_nonempty,
)


def normalize_tei(
    raw_tei_path: Path,
    *,
    input_file: Path,
    runtime_seconds: float,
    tool_version: str | None,
) -> NormalizedResult:
    """Normalize only explicit TEI fields; no title or reading-order heuristics."""

    root = ElementTree.parse(raw_tei_path).getroot()
    fields = extract_tei_fields(root)

    return NormalizedResult(
        tool="grobid",
        tool_version=tool_version,
        input_file=input_file.name,
        runtime_seconds=runtime_seconds,
        success=True,
        title=fields.title,
        authors=list(fields.authors),
        affiliations=list(fields.affiliations),
        abstract=fields.abstract,
        doi=fields.doi,
        sections=list(
            unique_nonempty(
                [
                    heading
                    for heading in (
                        element_text(node)
                        for node in root.findall(".//tei:text/tei:body//tei:head", TEI)
                    )
                    if heading
                ]
            )
        ),
        references=[{"text": reference} for reference in fields.references],
        tables=[
            {
                "label": element_text(node.find("tei:label", TEI)),
                "caption": element_text(node.find("tei:figDesc", TEI)),
                "coordinates": node.get("coords"),
            }
            for node in root.findall(".//tei:figure[@type='table']", TEI)
        ],
        figures=[
            {
                "label": element_text(node.find("tei:label", TEI)),
                "caption": element_text(node.find("tei:figDesc", TEI)),
                "coordinates": node.get("coords"),
            }
            for node in root.findall(".//tei:figure", TEI)
            if node.get("type") != "table"
        ],
        equations=[
            {"text": element_text(node), "coordinates": node.get("coords")}
            for node in root.findall(".//tei:formula", TEI)
        ],
        full_text=fields.full_text,
        has_coordinates=fields.has_coordinates,
        native_output=str(raw_tei_path),
    )
