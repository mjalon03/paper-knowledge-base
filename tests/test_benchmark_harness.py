from __future__ import annotations

import json
from pathlib import Path

from benchmark.adapters.docling import normalize_docling
from benchmark.scripts.create_synthetic_scan import create_image_only_pdf
from benchmark.scripts.evaluate_results import evaluate


def test_ground_truth_references_the_three_local_documents() -> None:
    manifest = json.loads(Path("benchmark/config/ground_truth.json").read_text())
    assert {item["filename"] for item in manifest["documents"]} == {
        path.name for path in Path("data").glob("*.pdf")
    }


def test_synthetic_scan_has_no_selectable_text(tmp_path: Path) -> None:
    source = next(Path("data").glob("*.pdf"))
    destination = tmp_path / "synthetic-scan.pdf"

    assert create_image_only_pdf(source, destination, pages=1, dpi=100) == 0
    assert destination.is_file()


def test_evaluation_only_awards_explicit_normalized_fields() -> None:
    truth = {
        "filename": "paper.pdf",
        "title": "A Paper",
        "authors": ["Author One"],
        "doi": "10.1/example",
        "abstract_beginning": "Expected abstract",
        "major_sections": ["Introduction"],
    }
    result = {
        "success": True,
        "title": "A Paper",
        "authors": ["Author One", "Different Person"],
        "doi": "10.1/example",
        "abstract": "Expected abstract text.",
        "sections": ["Introduction"],
        "references": [{"text": "Reference"}],
        "runtime_seconds": 1.0,
    }

    evaluation = evaluate(result, truth)

    assert evaluation["title_exact"]
    assert evaluation["doi_exact"]
    assert evaluation["authors_found"] == ["Author One"]
    assert evaluation["authors_unexpected"] == ["Different Person"]
    assert not evaluation["authors_exact"]
    assert evaluation["reference_count"] == 1


def test_docling_normalizer_keeps_missing_academic_metadata_empty(
    tmp_path: Path,
) -> None:
    raw_json = tmp_path / "document.json"
    raw_markdown = tmp_path / "document.md"
    raw_json.write_text(
        json.dumps(
            {
                "texts": [
                    {"label": "section_header", "text": "A heading", "prov": [{}]},
                    {"label": "text", "text": "Paragraph", "prov": [{}]},
                ],
                "tables": [{"label": "table", "data": {"table_cells": [{}]}}],
                "pictures": [{"label": "picture", "captions": []}],
            }
        )
    )
    raw_markdown.write_text("# A heading\n")

    result = normalize_docling(
        raw_json,
        raw_markdown,
        input_file=Path("paper.pdf"),
        runtime_seconds=1.0,
        tool_version="test",
        runtime_metadata={},
    )

    assert result.title is None
    assert result.sections == ["A heading"]
    assert len(result.tables) == 1
    assert result.has_coordinates
