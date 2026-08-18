from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark.adapters.models import NormalizedResult


def normalize_docling(
    raw_json_path: Path,
    raw_markdown_path: Path,
    *,
    input_file: Path,
    runtime_seconds: float,
    tool_version: str,
    runtime_metadata: dict[str, Any],
) -> NormalizedResult:
    """Map Docling's declared document objects without inventing metadata fields."""

    document = json.loads(raw_json_path.read_text(encoding="utf-8"))
    texts = document.get("texts", [])
    text_values = [item["text"] for item in texts if item.get("text")]
    section_headers = [
        item["text"]
        for item in texts
        if item.get("label") == "section_header" and item.get("text")
    ]
    return NormalizedResult(
        tool="docling",
        tool_version=tool_version,
        input_file=input_file.name,
        runtime_seconds=runtime_seconds,
        success=True,
        sections=section_headers,
        tables=[
            {
                "label": item.get("label"),
                "cells": len(item.get("data", {}).get("table_cells", [])),
                "coordinates": item.get("prov", []),
            }
            for item in document.get("tables", [])
        ],
        figures=[
            {
                "label": item.get("label"),
                "captions": item.get("captions", []),
                "coordinates": item.get("prov", []),
            }
            for item in document.get("pictures", [])
        ],
        full_text="\n\n".join(text_values),
        markdown=raw_markdown_path.read_text(encoding="utf-8"),
        has_coordinates=any(item.get("prov") for item in texts),
        native_output=str(raw_json_path.parent),
        runtime_metadata=runtime_metadata,
    )
