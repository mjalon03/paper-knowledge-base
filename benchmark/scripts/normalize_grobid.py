"""Recreate GROBID's normalized benchmark summary from saved TEI XML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark.adapters.grobid import normalize_tei


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--version", default="0.9.1")
    args = parser.parse_args()
    raw_path = args.output_dir / "raw" / f"{args.input_pdf.stem}.tei.xml"
    prior = json.loads(
        (args.output_dir / "normalized" / f"{args.input_pdf.stem}.json").read_text()
    )
    result = normalize_tei(
        raw_path,
        input_file=args.input_pdf,
        runtime_seconds=prior["runtime_seconds"],
        tool_version=args.version,
    )
    result.runtime_metadata = prior["runtime_metadata"]
    result.write_json(args.output_dir / "normalized" / f"{args.input_pdf.stem}.json")


if __name__ == "__main__":
    main()
