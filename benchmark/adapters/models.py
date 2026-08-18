from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class NormalizedResult:
    """Loss-aware benchmark summary; native output remains the source record."""

    tool: str
    tool_version: str | None
    input_file: str
    runtime_seconds: float
    success: bool
    error: str | None = None
    authors: list[str] = field(default_factory=list)
    affiliations: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    equations: list[dict[str, Any]] = field(default_factory=list)
    title: str | None = None
    abstract: str | None = None
    doi: str | None = None
    full_text: str | None = None
    markdown: str | None = None
    has_coordinates: bool = False
    native_output: str | None = None
    runtime_metadata: dict[str, Any] = field(default_factory=dict)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            __import__("json").dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
