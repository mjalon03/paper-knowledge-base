from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from benchmark.adapters.models import NormalizedResult

TEI = {"tei": "http://www.tei-c.org/ns/1.0"}


def _text(element: ElementTree.Element | None) -> str | None:
    if element is None:
        return None
    value = " ".join(" ".join(element.itertext()).split())
    return value or None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def normalize_tei(
    raw_tei_path: Path,
    *,
    input_file: Path,
    runtime_seconds: float,
    tool_version: str | None,
) -> NormalizedResult:
    """Normalize only explicit TEI fields; no title or reading-order heuristics."""

    root = ElementTree.parse(raw_tei_path).getroot()
    header = root.find("tei:teiHeader", TEI)
    authors: list[str] = []
    for author in root.findall(
        ".//tei:teiHeader/tei:fileDesc/tei:sourceDesc/tei:biblStruct/"
        "tei:analytic/tei:author",
        TEI,
    ):
        names = [_text(name) for name in author.findall(".//tei:persName", TEI)]
        authors.extend(name for name in names if name)

    references = []
    for reference in root.findall(".//tei:listBibl/tei:biblStruct", TEI):
        references.append({"text": _text(reference)})

    return NormalizedResult(
        tool="grobid",
        tool_version=tool_version,
        input_file=input_file.name,
        runtime_seconds=runtime_seconds,
        success=True,
        title=_text(root.find(".//tei:titleStmt/tei:title[@type='main']", TEI))
        or _text(root.find(".//tei:titleStmt/tei:title", TEI)),
        authors=_unique(authors),
        affiliations=_unique(
            [
                affiliation
                for affiliation in (
                    _text(node)
                    for node in (
                        header.findall(".//tei:affiliation", TEI) if header else []
                    )
                )
                if affiliation
            ]
        ),
        abstract=_text(root.find(".//tei:profileDesc/tei:abstract", TEI)),
        doi=_text(
            header.find(
                ".//tei:fileDesc/tei:sourceDesc/tei:biblStruct/tei:idno[@type='DOI']",
                TEI,
            )
            if header is not None
            else None
        ),
        sections=_unique(
            [
                heading
                for heading in (
                    _text(node)
                    for node in root.findall(".//tei:text/tei:body//tei:head", TEI)
                )
                if heading
            ]
        ),
        references=references,
        tables=[
            {
                "label": _text(node.find("tei:label", TEI)),
                "caption": _text(node.find("tei:figDesc", TEI)),
                "coordinates": node.get("coords"),
            }
            for node in root.findall(".//tei:figure[@type='table']", TEI)
        ],
        figures=[
            {
                "label": _text(node.find("tei:label", TEI)),
                "caption": _text(node.find("tei:figDesc", TEI)),
                "coordinates": node.get("coords"),
            }
            for node in root.findall(".//tei:figure", TEI)
            if node.get("type") != "table"
        ],
        equations=[
            {"text": _text(node), "coordinates": node.get("coords")}
            for node in root.findall(".//tei:formula", TEI)
        ],
        full_text=_text(root.find(".//tei:text/tei:body", TEI)),
        has_coordinates=any("coords" in element.attrib for element in root.iter()),
        native_output=str(raw_tei_path),
    )
