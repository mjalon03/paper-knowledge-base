from __future__ import annotations

import json
from pathlib import Path
from typing import Self

from paper_knowledge_base.metadata.models import (
    ResolutionStatus,
    SourceAuthor,
    SourceRecord,
)
from paper_knowledge_base.metadata.normalization import (
    author_overlap,
    normalize_author_name,
    normalize_doi,
    normalize_title,
    title_similarity,
)
from paper_knowledge_base.metadata.resolver import resolve_metadata
from paper_knowledge_base.metadata.sources.base import MetadataSourceUnavailableError
from paper_knowledge_base.metadata.sources.crossref import CrossrefClient
from paper_knowledge_base.metadata.sources.openalex import OpenAlexClient
from paper_knowledge_base.processing.models import (
    Author,
    DocumentContent,
    FileInfo,
    MetadataField,
    PaperProcessingResult,
    PDFInspection,
    ProcessingRoute,
    ProcessingStatus,
    ScholarlyMetadata,
)

TITLE = "Astrocytic Calcium Signaling Toolkit (astroCaST): efficient analysis"
DOI = "10.1000/astrocast"
EXTERNAL_AUTHORS = ("Ada Author", "Bea Biologist", "Chen Scientist", "Dev Researcher")


class FakeSource:
    def __init__(
        self,
        source: str,
        *,
        doi_record: SourceRecord | None = None,
        search_records: tuple[SourceRecord, ...] = (),
        error: Exception | None = None,
    ) -> None:
        self.source = source
        self.doi_record = doi_record
        self.search_records = search_records
        self.error = error

    def lookup_doi(self, doi: str) -> SourceRecord | None:
        if self.error:
            raise self.error
        return self.doi_record

    def search(
        self, title: str, *, year: int | None = None
    ) -> tuple[SourceRecord, ...]:
        if self.error:
            raise self.error
        return self.search_records


def record(
    source: str,
    *,
    doi: str = DOI,
    title: str = TITLE,
    authors: tuple[str, ...] = EXTERNAL_AUTHORS,
    year: int = 2024,
    work_type: str = "journal-article",
) -> SourceRecord:
    return SourceRecord(
        source=source,
        source_id=f"{source}:record",
        doi=doi,
        title=title,
        authors=tuple(SourceAuthor(name) for name in authors),
        year=year,
        venue="Example Journal",
        work_type=work_type,
        identifiers={source: f"{source}:record"},
    )


def processing_result(
    *, doi: str | None = None, title: str = TITLE
) -> PaperProcessingResult:
    return PaperProcessingResult(
        file=FileInfo(Path("paper.pdf"), "paper.pdf", 1, "0" * 64),
        inspection=PDFInspection(1, 1000, 1, 1.0, 1000.0, True),
        route=ProcessingRoute.EMBEDDED_TEXT,
        status=ProcessingStatus.SUCCESS,
        scholarly=ScholarlyMetadata(
            title=MetadataField(title, "grobid"),
            doi=MetadataField(doi, "grobid" if doi else None),
            authors=tuple(
                Author(name, "grobid")
                for name in (*EXTERNAL_AUTHORS, "Editor One", "Reviewer Two")
            ),
        ),
        document=DocumentContent(),
        parser_runs={},
    )


def test_doi_normalization_preserves_semantic_identifier() -> None:
    assert normalize_doi(" https://doi.org/10.1234/AbC.1). ") == "10.1234/abc.1"
    assert normalize_doi("DOI: 10.1234/ABC") == "10.1234/abc"
    assert normalize_doi("not a doi") is None


def test_title_and_author_normalization_are_conservative() -> None:
    assert normalize_title("Ca2+ β-astrocyte: STARDUST.") == "ca2+ β-astrocyte stardust"
    assert normalize_author_name("Áda L. Author") == "áda l author"
    assert title_similarity("astroCaST", "astrocast") > 0.9
    assert author_overlap(["A. Author"], ["Ada Author"]) == 1.0


def test_crossref_client_normalizes_mocked_doi_response() -> None:
    seen_urls: list[str] = []

    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "message": {
                        "DOI": "10.1000/ASTROCAST",
                        "title": [TITLE],
                        "author": [{"given": "Ada", "family": "Author"}],
                        "issued": {"date-parts": [[2024]]},
                        "container-title": ["Example Journal"],
                    }
                }
            ).encode()

    def opener(request: object, timeout: float) -> Response:
        seen_urls.append(request.full_url)
        return Response()

    result = CrossrefClient(mailto="maintainer@example.org", opener=opener).lookup_doi(
        DOI
    )

    assert result is not None
    assert result.doi == DOI
    assert result.authors[0].display_name == "Ada Author"
    assert "works/doi/10.1000/astrocast" in seen_urls[0]
    assert "mailto=maintainer%40example.org" in seen_urls[0]


def test_openalex_client_normalizes_mocked_search_response() -> None:
    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W1",
                            "doi": "https://doi.org/10.1000/ASTROCAST",
                            "display_name": TITLE,
                            "publication_year": 2024,
                            "authorships": [{"author": {"display_name": "Ada Author"}}],
                            "primary_location": {
                                "source": {"display_name": "Example Journal"}
                            },
                        }
                    ]
                }
            ).encode()

    result = OpenAlexClient(opener=lambda request, timeout: Response()).search(TITLE)

    assert result[0].source_id == "https://openalex.org/W1"
    assert result[0].doi == DOI
    assert result[0].venue == "Example Journal"


def test_exact_doi_verified_by_crossref_and_openalex() -> None:
    result = resolve_metadata(
        processing_result(doi=f"https://doi.org/{DOI}"),
        crossref=FakeSource("crossref", doi_record=record("crossref")),
        openalex=FakeSource("openalex", doi_record=record("openalex")),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.metadata.doi.value == DOI
    assert {item.source for item in result.metadata.doi.provenance} == {
        "crossref",
        "openalex",
    }


def test_missing_doi_is_recovered_and_spurious_parser_authors_remain_evidence() -> None:
    result = resolve_metadata(
        processing_result(),
        crossref=FakeSource("crossref", search_records=(record("crossref"),)),
        openalex=FakeSource("openalex", search_records=(record("openalex"),)),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.metadata.doi.value == DOI
    assert len(result.metadata.authors) == 4
    assert len(result.candidate.authors) == 6
    assert "Reviewer Two" in result.candidate.authors


def test_title_mismatch_prevents_bad_doi_acceptance() -> None:
    result = resolve_metadata(
        processing_result(doi=DOI, title="Entirely unrelated paper"),
        crossref=FakeSource("crossref", doi_record=record("crossref")),
        openalex=FakeSource("openalex", doi_record=record("openalex")),
    )

    assert result.status == ResolutionStatus.CONFLICT
    assert result.metadata.doi.value == DOI
    assert result.conflicts


def test_one_source_failure_degrades_to_partial_resolution() -> None:
    result = resolve_metadata(
        processing_result(doi=DOI),
        crossref=FakeSource("crossref", doi_record=record("crossref")),
        openalex=FakeSource(
            "openalex", error=MetadataSourceUnavailableError("offline")
        ),
    )

    assert result.status == ResolutionStatus.PARTIALLY_RESOLVED
    assert result.metadata.doi.value == DOI
    assert result.evidence[-1].error_type == "MetadataSourceUnavailableError"


def test_both_source_failures_return_unverified_candidate() -> None:
    result = resolve_metadata(
        processing_result(doi=DOI),
        crossref=FakeSource(
            "crossref", error=MetadataSourceUnavailableError("offline")
        ),
        openalex=FakeSource(
            "openalex", error=MetadataSourceUnavailableError("offline")
        ),
    )

    assert result.status == ResolutionStatus.UNVERIFIED
    assert result.metadata.doi.value == DOI
    assert len(result.candidate.authors) == 6


def test_conflicting_external_dois_are_not_silently_chosen() -> None:
    result = resolve_metadata(
        processing_result(),
        crossref=FakeSource(
            "crossref", search_records=(record("crossref", doi="10.1000/a"),)
        ),
        openalex=FakeSource(
            "openalex", search_records=(record("openalex", doi="10.1000/b"),)
        ),
    )

    assert result.status == ResolutionStatus.CONFLICT


def test_journal_record_breaks_a_tie_against_preprint_records() -> None:
    journal_crossref = record("crossref", doi="10.1000/journal")
    preprint_crossref = record(
        "crossref",
        doi="10.1000/preprint",
        work_type="posted-content",
    )
    journal_openalex = record("openalex", doi="10.1000/journal", work_type="article")
    preprint_openalex = record("openalex", doi="10.1000/preprint", work_type="preprint")

    result = resolve_metadata(
        processing_result(),
        crossref=FakeSource(
            "crossref", search_records=(preprint_crossref, journal_crossref)
        ),
        openalex=FakeSource(
            "openalex", search_records=(journal_openalex, preprint_openalex)
        ),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.metadata.doi.value == "10.1000/journal"


def test_low_confidence_title_search_stays_unverified() -> None:
    result = resolve_metadata(
        processing_result(title="Completely different candidate"),
        crossref=FakeSource("crossref", search_records=(record("crossref"),)),
        openalex=FakeSource("openalex", search_records=()),
    )

    assert result.status == ResolutionStatus.UNVERIFIED
    assert result.metadata.doi.value is None
