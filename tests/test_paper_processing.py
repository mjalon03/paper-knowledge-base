from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Self
from urllib.error import URLError

import pymupdf
import pytest

from paper_knowledge_base.parsers.docling import (
    DoclingAdapter,
    DoclingParseOutput,
    DoclingUnavailableError,
    normalize_docling_document,
)
from paper_knowledge_base.parsers.grobid import (
    GrobidAdapter,
    GrobidParseOutput,
    GrobidRequestError,
    normalize_tei_xml,
)
from paper_knowledge_base.processing.inspection import inspect_embedded_text
from paper_knowledge_base.processing.models import (
    DocumentContent,
    MetadataField,
    ParserStatus,
    ProcessingRoute,
    ProcessingStatus,
)
from paper_knowledge_base.processing.pipeline import process_paper

TEI_WITH_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader><fileDesc><titleStmt><title type="main">Example paper</title></titleStmt>
  <sourceDesc><biblStruct><analytic><author><persName>Ada Author</persName></author></analytic>
  <idno type="DOI">10.1000/example</idno></biblStruct><affiliation>Example Lab</affiliation></sourceDesc></fileDesc>
  <profileDesc><abstract>Example abstract.</abstract></profileDesc></teiHeader>
  <text><body><div><head>Introduction</head><p>First section text.</p></div></body>
  <back><listBibl><biblStruct>One reference</biblStruct></listBibl></back></text>
</TEI>"""


def create_text_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    for index in range(12):
        page.insert_text((72, 72 + index * 32), "Meaningful embedded text " * 7)
    document.save(path)
    document.close()


def create_image_only_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.draw_rect(pymupdf.Rect(72, 72, 400, 400), fill=(0.2, 0.2, 0.2))
    document.save(path)
    document.close()


class FakeGrobid:
    name = "grobid"
    version = "test"

    def __init__(
        self, output: GrobidParseOutput | None = None, error: Exception | None = None
    ) -> None:
        self.output = output or GrobidParseOutput(
            scholarly=normalize_tei_xml(TEI_WITH_METADATA),
            raw_tei_xml=TEI_WITH_METADATA,
        )
        self.error = error
        self.called = False

    def parse(self, path: Path) -> GrobidParseOutput:
        self.called = True
        if self.error:
            raise self.error
        return self.output


class FakeDocling:
    name = "docling"
    version = "test"

    def __init__(
        self, output: DoclingParseOutput | None = None, error: Exception | None = None
    ) -> None:
        self.output = output or DoclingParseOutput(
            document=DocumentContent(
                markdown="# Example paper\n",
                text="Example paper",
                structured={"texts": [{"text": "Example paper"}]},
                source="docling",
            ),
            raw_document={"texts": [{"text": "Example paper"}]},
        )
        self.error = error
        self.ocr_arguments: list[bool] = []

    def parse(self, path: Path, *, ocr: bool) -> DoclingParseOutput:
        self.ocr_arguments.append(ocr)
        if self.error:
            raise self.error
        return self.output


def test_embedded_text_inspection_uses_documented_coverage_heuristic(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "embedded.pdf"
    create_text_pdf(pdf_path)

    inspection = inspect_embedded_text(pdf_path)

    assert inspection.has_usable_embedded_text
    assert inspection.page_count == 1
    assert inspection.pages_with_meaningful_text == 1
    assert inspection.text_character_count >= 300


def test_image_only_pdf_inspection_routes_to_ocr(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    create_image_only_pdf(pdf_path)

    inspection = inspect_embedded_text(pdf_path)

    assert not inspection.has_usable_embedded_text
    assert inspection.text_character_count == 0
    assert inspection.pages_with_meaningful_text == 0


def test_grobid_normalization_retains_provenance_and_missing_doi() -> None:
    successful = normalize_tei_xml(TEI_WITH_METADATA)
    missing_doi = normalize_tei_xml(TEI_WITH_METADATA.replace("10.1000/example", ""))

    assert successful.title == MetadataField("Example paper", "grobid")
    assert successful.authors[0].source == "grobid"
    assert successful.sections[0].heading == "Introduction"
    assert successful.references[0].text == "One reference"
    assert missing_doi.doi == MetadataField(None, None)


def test_grobid_adapter_normalizes_mocked_http_response(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_text_pdf(pdf_path)

    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return TEI_WITH_METADATA.encode()

    adapter = GrobidAdapter(opener=lambda request, timeout: Response())
    result = adapter.parse(pdf_path)

    assert result.scholarly.title.value == "Example paper"
    assert result.raw_tei_xml == TEI_WITH_METADATA


def test_grobid_adapter_exposes_request_failure(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_text_pdf(pdf_path)
    adapter = GrobidAdapter(
        opener=lambda request, timeout: (_ for _ in ()).throw(URLError("offline"))
    )

    with pytest.raises(GrobidRequestError, match="request failed"):
        adapter.parse(pdf_path)


def test_docling_adapter_normalizes_command_output(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_text_pdf(pdf_path)

    def runner(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        output = Path(command[command.index("--output") + 1])
        (output / "paper.json").write_text(
            json.dumps({"texts": [{"label": "text", "text": "Recovered text"}]}),
            encoding="utf-8",
        )
        (output / "paper.md").write_text("# Recovered text\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    result = DoclingAdapter(runner=runner).parse(pdf_path, ocr=True)

    assert result.document.markdown == "# Recovered text\n"
    assert result.document.text == "Recovered text"
    assert result.document.ocr_used
    assert result.raw_document["texts"][0]["text"] == "Recovered text"


def test_docling_adapter_exposes_missing_executable(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_text_pdf(pdf_path)
    adapter = DoclingAdapter(
        executable="missing-docling",
        runner=lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    with pytest.raises(DoclingUnavailableError, match="not found"):
        adapter.parse(pdf_path, ocr=False)


def test_docling_normalization_preserves_native_structure() -> None:
    raw = {"texts": [{"text": "One"}], "tables": [{"label": "table"}]}

    result = normalize_docling_document(raw, "# One\n", ocr_used=False)

    assert result.structured == raw
    assert result.source == "docling"
    assert result.ocr_used is False


def test_born_digital_routing_runs_both_parsers_and_preserves_sha(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_text_pdf(pdf_path)
    grobid = FakeGrobid()
    docling = FakeDocling()

    result = process_paper(pdf_path, grobid=grobid, docling=docling)

    assert result.route == ProcessingRoute.EMBEDDED_TEXT
    assert result.status == ProcessingStatus.SUCCESS
    assert grobid.called
    assert docling.ocr_arguments == [False]
    assert (
        result.file.sha256
        == __import__("hashlib").sha256(pdf_path.read_bytes()).hexdigest()
    )
    assert result.scholarly.title.source == "grobid"
    assert result.parser_runs["grobid"].raw_output == TEI_WITH_METADATA


def test_scan_routing_skips_grobid_and_runs_docling_ocr(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    create_image_only_pdf(pdf_path)
    grobid = FakeGrobid()
    docling = FakeDocling()

    result = process_paper(pdf_path, grobid=grobid, docling=docling)

    assert result.route == ProcessingRoute.OCR_FALLBACK
    assert result.status == ProcessingStatus.SUCCESS
    assert not grobid.called
    assert result.parser_runs["grobid"].status == ParserStatus.SKIPPED
    assert docling.ocr_arguments == [True]


def test_one_parser_failure_preserves_other_parser_output(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_text_pdf(pdf_path)

    result = process_paper(
        pdf_path,
        grobid=FakeGrobid(),
        docling=FakeDocling(error=RuntimeError("model unavailable")),
    )

    assert result.status == ProcessingStatus.PARTIAL_SUCCESS
    assert result.scholarly.title.value == "Example paper"
    assert result.parser_runs["docling"].status == ParserStatus.FAILED
    assert result.parser_runs["docling"].error_type == "RuntimeError"


def test_complete_parser_failure_returns_failed_result(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    create_text_pdf(pdf_path)

    result = process_paper(
        pdf_path,
        grobid=FakeGrobid(error=RuntimeError("service unavailable")),
        docling=FakeDocling(error=RuntimeError("model unavailable")),
    )

    assert result.status == ProcessingStatus.FAILED
    assert {run.status for run in result.parser_runs.values()} == {ParserStatus.FAILED}
