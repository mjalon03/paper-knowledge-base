from __future__ import annotations

import json
from pathlib import Path

from paper_knowledge_base.content import (
    ContentStatus,
    Figure,
    Paragraph,
    Table,
    build_paper_content,
)
from paper_knowledge_base.processing.models import (
    DocumentContent,
    FileInfo,
    MetadataField,
    PaperProcessingResult,
    ParserRun,
    ParserStatus,
    PDFInspection,
    ProcessingRoute,
    ProcessingStatus,
    ScholarlyMetadata,
)

TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader><fileDesc><titleStmt><title type="main">Example</title></titleStmt>
    <sourceDesc><biblStruct><analytic><author><persName><forename>Ada</forename><surname>Author</surname></persName></author></analytic>
      <idno type="DOI">10.1000/example</idno></biblStruct></sourceDesc></fileDesc>
  </teiHeader>
  <text><front><abstract>Canonical abstract with Ca²⁺.</abstract></front><body>
    <div xml:id="d1"><head>1 Introduction</head>
      <p coords="2,10,20,100,30">Events use <ref type="bibr" target="#b0">[1]</ref> and preserve β.</p>
      <div xml:id="d2"><head>1.1 Imaging</head><p>Second paragraph.</p></div>
      <figure xml:id="f1"><label>Figure 1</label><figDesc>Example image.</figDesc><graphic url="figure-1.png"/></figure>
      <formula xml:id="eq1">E = mc²</formula>
    </div>
  </body><back><listBibl><biblStruct xml:id="b0"><label>1</label><analytic><title>Reference title</title><author><persName><surname>Smith</surname></persName></author></analytic><monogr><title>Journal</title><imprint><date when="2020"/></imprint></monogr><idno type="DOI">10.1000/ref</idno></biblStruct></listBibl></back></text>
</TEI>"""


def _docling() -> dict[str, object]:
    return {
        "body": {
            "children": [
                {"$ref": "#/texts/0"},
                {"$ref": "#/texts/1"},
                {"$ref": "#/texts/2"},
                {"$ref": "#/pictures/0"},
                {"$ref": "#/tables/0"},
            ]
        },
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "page_header",
                "text": "Journal",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/1",
                "label": "section_header",
                "text": "1 Introduction",
                "prov": [{"page_no": 1}],
            },
            {
                "self_ref": "#/texts/2",
                "label": "text",
                "text": "A paragraph with Ω and scientific content.",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 1,
                            "t": 2,
                            "r": 3,
                            "b": 4,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            },
            {
                "self_ref": "#/texts/3",
                "label": "caption",
                "text": "Figure 1. Docling caption.",
                "prov": [{"page_no": 1}],
            },
        ],
        "pictures": [
            {
                "self_ref": "#/pictures/0",
                "label": "picture",
                "captions": [{"$ref": "#/texts/3"}],
                "image": {"uri": "data:image/png;base64,secret-bytes"},
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 5,
                            "t": 6,
                            "r": 7,
                            "b": 8,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            }
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "label": "Table 1",
                "captions": [],
                "data": {
                    "table_cells": [
                        {
                            "text": "A",
                            "column_header": True,
                            "start_row_offset_idx": 0,
                            "start_col_offset_idx": 0,
                        },
                        {
                            "text": "B",
                            "column_header": True,
                            "start_row_offset_idx": 0,
                            "start_col_offset_idx": 1,
                        },
                        {
                            "text": "1",
                            "start_row_offset_idx": 1,
                            "start_col_offset_idx": 0,
                        },
                        {
                            "text": "2",
                            "start_row_offset_idx": 1,
                            "start_col_offset_idx": 1,
                        },
                    ]
                },
                "prov": [
                    {
                        "page_no": 2,
                        "bbox": {
                            "l": 10,
                            "t": 20,
                            "r": 30,
                            "b": 40,
                            "coord_origin": "TOPLEFT",
                        },
                    }
                ],
            }
        ],
    }


def _result(
    *,
    tei: str | None = TEI,
    docling: dict[str, object] | None = None,
    grobid_status: ParserStatus = ParserStatus.SUCCESS,
    docling_status: ParserStatus = ParserStatus.SUCCESS,
) -> PaperProcessingResult:
    return PaperProcessingResult(
        file=FileInfo(Path("paper.pdf"), "paper.pdf", 10, "a" * 64),
        inspection=PDFInspection(2, 100, 2, 1.0, 50, True),
        route=ProcessingRoute.EMBEDDED_TEXT,
        status=ProcessingStatus.SUCCESS,
        scholarly=ScholarlyMetadata(
            abstract=MetadataField("Canonical abstract with Ca²⁺.", "grobid")
        ),
        document=DocumentContent(structured=docling, source="docling"),
        parser_runs={
            "grobid": ParserRun("grobid", grobid_status, 1.0, "0.9.1", raw_output=tei),
            "docling": ParserRun(
                "docling", docling_status, 1.0, "2.120.2", raw_output=docling
            ),
        },
    )


def test_grobid_content_recovers_hierarchy_citations_and_assets() -> None:
    content = build_paper_content(
        _result(docling=None, docling_status=ParserStatus.FAILED)
    )

    assert content.status is ContentStatus.PARTIAL
    assert [section.title for section in content.sections] == [
        "Abstract",
        "Introduction",
        "Imaging",
    ]
    assert content.sections[-1].parent_id == content.sections[-2].id
    paragraphs = [block for block in content.blocks if isinstance(block, Paragraph)]
    assert paragraphs[1].text.endswith("β.")
    assert content.citations[0].reference_ids == (content.references[0].id,)
    assert content.citations[0].start is not None
    assert any(isinstance(block, Figure) for block in content.blocks)
    assert any(
        isinstance(block, object) and block.block_type.value == "equation"
        for block in content.blocks
    )
    assert content.references[0].doi == "10.1000/ref"


def test_docling_only_content_filters_noise_and_preserves_layout() -> None:
    result = _result(tei=None, docling=_docling(), grobid_status=ParserStatus.SKIPPED)
    result = PaperProcessingResult(
        file=result.file,
        inspection=result.inspection,
        route=ProcessingRoute.OCR_FALLBACK,
        status=result.status,
        scholarly=ScholarlyMetadata(),
        document=result.document,
        parser_runs=result.parser_runs,
    )
    content = build_paper_content(result)

    assert content.status is ContentStatus.COMPLETE
    assert all("Journal" not in getattr(block, "text", "") for block in content.blocks)
    figure = next(block for block in content.blocks if isinstance(block, Figure))
    table = next(block for block in content.blocks if isinstance(block, Table))
    assert figure.asset_ref == "docling:#/pictures/0"
    assert figure.source_location and figure.source_location.page_number == 1
    assert (
        figure.source_location.bbox
        and figure.source_location.bbox.coordinate_origin == "BOTTOMLEFT"
    )
    assert table.headers == ("A", "B")
    assert table.rows == (("1", "2"),)


def test_cross_parser_merge_uses_grobid_text_and_docling_assets() -> None:
    content = build_paper_content(_result(docling=_docling()))

    assert content.status is ContentStatus.COMPLETE
    assert any(
        block.provenance[0].parser == "grobid"
        for block in content.blocks
        if isinstance(block, Paragraph)
    )
    assert any(
        block.provenance[0].parser == "docling"
        for block in content.blocks
        if isinstance(block, Figure)
    )
    assert not any(
        isinstance(block, Paragraph) and block.provenance[0].parser == "docling"
        for block in content.blocks
    )


def test_serialization_is_stable_json_and_keeps_scientific_unicode() -> None:
    content = build_paper_content(
        _result(docling=None, docling_status=ParserStatus.FAILED)
    )
    first = content.to_json()
    second = content.to_json()

    assert first == second
    decoded = json.loads(first)
    assert decoded["source_document_sha256"] == "a" * 64
    assert "grobid" not in json.dumps(decoded["blocks"][0].get("raw", {}))
    assert "Ca²⁺" in first
    assert "secret-bytes" not in content.to_json()


def test_mobile_debug_renderer_consumes_canonical_json() -> None:
    from scripts.render_mobile_article import render_mobile_article

    content = build_paper_content(
        _result(docling=None, docling_status=ParserStatus.FAILED)
    )
    rendered = render_mobile_article(content.to_dict())

    assert "<article>" in rendered
    assert "Introduction" in rendered
    assert "References" in rendered
    assert "paper_knowledge_base.parsers" not in rendered
