"""Normalize a completed Docling CLI run while keeping its JSON and Markdown intact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark.adapters.docling import normalize_docling


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--version", default="2.120.2")
    args = parser.parse_args()
    raw_dir = args.output_dir / "raw"
    prior = json.loads(
        (args.output_dir / "normalized" / f"{args.input_pdf.stem}.json").read_text()
    )
    result = normalize_docling(
        raw_dir / f"{args.input_pdf.stem}.json",
        raw_dir / f"{args.input_pdf.stem}.md",
        input_file=args.input_pdf,
        runtime_seconds=prior["runtime_seconds"],
        tool_version=args.version,
        runtime_metadata=prior["runtime_metadata"],
    )
    result.write_json(args.output_dir / "normalized" / f"{args.input_pdf.stem}.json")


if __name__ == "__main__":
    main()
