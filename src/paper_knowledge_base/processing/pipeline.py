"""Route a PDF through mature scholarly and document parsers."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Protocol

from paper_knowledge_base.ingestion.pdf import PDFFileInfo, inspect_pdf
from paper_knowledge_base.parsers.docling import DoclingAdapter, DoclingParseOutput
from paper_knowledge_base.parsers.grobid import GrobidAdapter, GrobidParseOutput
from paper_knowledge_base.processing.inspection import (
    DEFAULT_TEXT_COVERAGE_THRESHOLDS,
    TextCoverageThresholds,
    inspect_embedded_text,
)
from paper_knowledge_base.processing.models import (
    DocumentContent,
    FileInfo,
    PaperProcessingResult,
    ParserRun,
    ParserStatus,
    ProcessingRoute,
    ProcessingStatus,
    ScholarlyMetadata,
)


class ScholarlyParser(Protocol):
    name: str
    version: str | None

    def parse(self, path: Path) -> GrobidParseOutput: ...


class DocumentParser(Protocol):
    name: str
    version: str | None

    def parse(self, path: Path, *, ocr: bool) -> DoclingParseOutput: ...


def process_paper(
    path: str | Path,
    *,
    grobid: ScholarlyParser | None = None,
    docling: DocumentParser | None = None,
    thresholds: TextCoverageThresholds = DEFAULT_TEXT_COVERAGE_THRESHOLDS,
) -> PaperProcessingResult:
    """Process one PDF while isolating parser failures in a unified result.

    Invalid input is raised by the existing ingestion/text-extraction utilities.
    Once inspection succeeds, parser failures are represented in ``parser_runs``
    rather than preventing useful output from the other parser.
    """

    file_info = inspect_pdf(path)
    inspection = inspect_embedded_text(file_info.path, thresholds=thresholds)
    route = (
        ProcessingRoute.EMBEDDED_TEXT
        if inspection.has_usable_embedded_text
        else ProcessingRoute.OCR_FALLBACK
    )
    grobid = grobid or GrobidAdapter()
    docling = docling or DoclingAdapter()
    parser_runs: dict[str, ParserRun] = {}
    scholarly = ScholarlyMetadata()
    document = DocumentContent()

    if route == ProcessingRoute.EMBEDDED_TEXT:
        output, parser_run = _run_grobid(grobid, file_info.path)
        parser_runs[grobid.name] = parser_run
        if output is not None:
            scholarly = output.scholarly
    else:
        parser_runs[grobid.name] = ParserRun(
            parser=grobid.name,
            status=ParserStatus.SKIPPED,
            runtime_seconds=None,
            version=grobid.version,
            error_message="Skipped because embedded text did not meet routing thresholds.",
        )

    docling_output, docling_run = _run_docling(
        docling,
        file_info.path,
        ocr=route == ProcessingRoute.OCR_FALLBACK,
    )
    parser_runs[docling.name] = docling_run
    if docling_output is not None:
        document = docling_output.document

    return PaperProcessingResult(
        file=_file_info(file_info),
        inspection=inspection,
        route=route,
        status=_processing_status(route, parser_runs),
        scholarly=scholarly,
        document=document,
        parser_runs=parser_runs,
    )


def _file_info(info: PDFFileInfo) -> FileInfo:
    return FileInfo(
        path=info.path,
        filename=info.filename,
        size_bytes=info.size_bytes,
        sha256=info.sha256,
    )


def _run_grobid(
    adapter: ScholarlyParser,
    path: Path,
) -> tuple[GrobidParseOutput | None, ParserRun]:
    started = time.monotonic()
    try:
        output = adapter.parse(path)
    except Exception as exc:  # noqa: BLE001 - parser boundary preserves peer output.
        return None, ParserRun(
            parser=adapter.name,
            status=ParserStatus.FAILED,
            runtime_seconds=time.monotonic() - started,
            version=adapter.version,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    return output, ParserRun(
        parser=adapter.name,
        status=ParserStatus.SUCCESS,
        runtime_seconds=time.monotonic() - started,
        version=adapter.version,
        raw_output=output.raw_tei_xml,
    )


def _run_docling(
    adapter: DocumentParser,
    path: Path,
    *,
    ocr: bool,
) -> tuple[DoclingParseOutput | None, ParserRun]:
    started = time.monotonic()
    try:
        output = adapter.parse(path, ocr=ocr)
    except Exception as exc:  # noqa: BLE001 - parser boundary preserves peer output.
        return None, ParserRun(
            parser=adapter.name,
            status=ParserStatus.FAILED,
            runtime_seconds=time.monotonic() - started,
            version=adapter.version,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    return output, ParserRun(
        parser=adapter.name,
        status=ParserStatus.SUCCESS,
        runtime_seconds=time.monotonic() - started,
        version=adapter.version,
        raw_output=output.raw_document,
    )


def _processing_status(
    route: ProcessingRoute,
    parser_runs: dict[str, ParserRun],
) -> ProcessingStatus:
    successful = sum(run.status == ParserStatus.SUCCESS for run in parser_runs.values())
    if successful == 0:
        return ProcessingStatus.FAILED
    if route == ProcessingRoute.OCR_FALLBACK:
        return ProcessingStatus.SUCCESS
    if successful == len(parser_runs):
        return ProcessingStatus.SUCCESS
    return ProcessingStatus.PARTIAL_SUCCESS


def _summary(result: PaperProcessingResult, *, verbose: bool) -> str:
    lines = [
        f"file: {result.file.filename}",
        f"sha256: {result.file.sha256}",
        f"pages: {result.inspection.page_count}",
        (
            f"embedded text: {result.inspection.has_usable_embedded_text} "
            f"({result.inspection.text_character_count} characters)"
        ),
        f"route: {result.route.value}",
        f"status: {result.status.value}",
    ]
    for name, run in result.parser_runs.items():
        line = f"{name}: {run.status.value}"
        if run.runtime_seconds is not None:
            line += f" ({run.runtime_seconds:.2f}s)"
        if verbose and run.error_message:
            line += f" — {run.error_type}: {run.error_message}"
        lines.append(line)
    if result.scholarly.title.value:
        lines.append(f"title: {result.scholarly.title.value}")
    if verbose:
        lines.extend(
            [
                f"authors: {len(result.scholarly.authors)}",
                f"doi: {result.scholarly.doi.value or 'missing'}",
                f"sections: {len(result.scholarly.sections)}",
                f"references: {len(result.scholarly.references)}",
                f"markdown characters: {len(result.document.markdown or '')}",
                f"OCR used: {result.document.ocr_used}",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process one academic PDF.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    print(_summary(process_paper(args.path), verbose=args.verbose))


if __name__ == "__main__":
    main()
