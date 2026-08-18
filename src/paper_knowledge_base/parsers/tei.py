"""Loss-aware extraction of the GROBID TEI fields used by this project."""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

TEI = {"tei": "http://www.tei-c.org/ns/1.0"}


def element_text(element: ElementTree.Element | None) -> str | None:
    """Return normalized text from an explicit TEI element."""

    if element is None:
        return None
    value = " ".join(" ".join(element.itertext()).split())
    return value or None


def unique_nonempty(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


@dataclass(frozen=True)
class TEISection:
    heading: str | None
    text: str | None


@dataclass(frozen=True)
class TEIFields:
    title: str | None
    authors: tuple[str, ...]
    affiliations: tuple[str, ...]
    abstract: str | None
    doi: str | None
    sections: tuple[TEISection, ...]
    references: tuple[str, ...]
    full_text: str | None
    has_coordinates: bool


def extract_tei_fields(root: ElementTree.Element) -> TEIFields:
    """Extract only explicit scholarly fields; do not infer missing metadata."""

    header = root.find("tei:teiHeader", TEI)
    authors: list[str] = []
    for author in root.findall(
        ".//tei:teiHeader/tei:fileDesc/tei:sourceDesc/tei:biblStruct/"
        "tei:analytic/tei:author",
        TEI,
    ):
        authors.extend(
            name
            for name in (
                element_text(node) for node in author.findall(".//tei:persName", TEI)
            )
            if name
        )

    sections: list[TEISection] = []
    for division in root.findall(".//tei:text/tei:body//tei:div", TEI):
        heading = element_text(division.find("tei:head", TEI))
        paragraphs = [
            text
            for text in (element_text(node) for node in division.findall("tei:p", TEI))
            if text
        ]
        if heading or paragraphs:
            sections.append(
                TEISection(heading=heading, text="\n\n".join(paragraphs) or None)
            )

    return TEIFields(
        title=element_text(root.find(".//tei:titleStmt/tei:title[@type='main']", TEI))
        or element_text(root.find(".//tei:titleStmt/tei:title", TEI)),
        authors=unique_nonempty(authors),
        affiliations=unique_nonempty(
            [
                affiliation
                for affiliation in (
                    element_text(node)
                    for node in (
                        header.findall(".//tei:affiliation", TEI)
                        if header is not None
                        else []
                    )
                )
                if affiliation
            ]
        ),
        abstract=element_text(root.find(".//tei:profileDesc/tei:abstract", TEI)),
        doi=element_text(
            header.find(
                ".//tei:fileDesc/tei:sourceDesc/tei:biblStruct/tei:idno[@type='DOI']",
                TEI,
            )
            if header is not None
            else None
        ),
        sections=tuple(sections),
        references=unique_nonempty(
            [
                reference
                for reference in (
                    element_text(node)
                    for node in root.findall(".//tei:listBibl/tei:biblStruct", TEI)
                )
                if reference
            ]
        ),
        full_text=element_text(root.find(".//tei:text/tei:body", TEI)),
        has_coordinates=any("coords" in element.attrib for element in root.iter()),
    )
