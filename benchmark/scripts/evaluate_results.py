"""Evaluate explicit normalized fields against a deliberately small local manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _normalized(value: str | None) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value or "").casefold().split())


def _contains(expected: str, observed: str | None) -> bool:
    return _normalized(expected) in _normalized(observed)


def _heading(value: str) -> str:
    return re.sub(r"^\d+(?:\s*\.\s*\d+)*\s+", "", _normalized(value))


def evaluate(result: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    authors = {_normalized(author) for author in result.get("authors", [])}
    expected_authors = {_normalized(author) for author in truth["authors"]}
    sections = result.get("sections", [])
    return {
        "input_file": truth["filename"],
        "success": result.get("success", False),
        "title_exact": _normalized(result.get("title")) == _normalized(truth["title"]),
        "doi_exact": _normalized(result.get("doi")) == _normalized(truth["doi"]),
        "authors_found": [
            author for author in truth["authors"] if _normalized(author) in authors
        ],
        "authors_expected": truth["authors"],
        "authors_unexpected": [
            author
            for author in result.get("authors", [])
            if _normalized(author) not in expected_authors
        ],
        "authors_exact": authors == expected_authors,
        "abstract_beginning_found": _contains(
            truth["abstract_beginning"], result.get("abstract")
        ),
        "major_sections_found": [
            heading
            for heading in truth["major_sections"]
            if any(_heading(heading) in _heading(observed) for observed in sections)
        ],
        "major_sections_expected": truth["major_sections"],
        "reference_count": len(result.get("references", [])),
        "runtime_seconds": result.get("runtime_seconds"),
        "error": result.get("error"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    evaluations = []
    for truth in manifest["documents"]:
        result_path = args.results_dir / f"{Path(truth['filename']).stem}.json"
        if result_path.exists():
            evaluations.append(evaluate(json.loads(result_path.read_text()), truth))
        else:
            evaluations.append(
                {
                    "input_file": truth["filename"],
                    "success": False,
                    "error": "normalized result is missing",
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"evaluations": evaluations}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
