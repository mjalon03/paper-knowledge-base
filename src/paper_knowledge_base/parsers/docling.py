"""Subprocess adapter for an optional, separately managed Docling environment."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paper_knowledge_base.processing.models import DocumentContent

DEFAULT_DOCLING_EXECUTABLE = "docling"
DEFAULT_DOCLING_TIMEOUT_SECONDS = 900.0


class DoclingError(Exception):
    """Base exception for optional Docling execution and normalization failures."""


class DoclingUnavailableError(DoclingError):
    """The configured Docling executable cannot be started."""


class DoclingProcessError(DoclingError):
    """Docling ran but did not produce a successful conversion."""


class DoclingOutputError(DoclingError):
    """Docling completed but did not produce readable Markdown and JSON."""


@dataclass(frozen=True)
class DoclingParseOutput:
    document: DocumentContent
    raw_document: dict[str, Any]


Runner = Callable[..., subprocess.CompletedProcess[str]]


class DoclingAdapter:
    """Run the Docling CLI without making its models a core package dependency.

    The benchmark proved Docling in an isolated environment. Keeping this adapter
    subprocess-based lets local operators select that environment through
    ``DOCLING_EXECUTABLE`` while fast unit tests use a fake adapter instead.
    """

    name = "docling"
    version = "2.120.2"

    def __init__(
        self,
        executable: str | None = None,
        timeout_seconds: float | None = None,
        device: str | None = None,
        *,
        runner: Runner | None = None,
    ) -> None:
        self.executable = executable or os.environ.get(
            "DOCLING_EXECUTABLE", DEFAULT_DOCLING_EXECUTABLE
        )
        self.timeout_seconds = timeout_seconds or float(
            os.environ.get("DOCLING_TIMEOUT", DEFAULT_DOCLING_TIMEOUT_SECONDS)
        )
        self.device = device or os.environ.get("DOCLING_DEVICE", "cpu")
        self._runner = runner or subprocess.run

    def parse(self, path: Path, *, ocr: bool) -> DoclingParseOutput:
        with tempfile.TemporaryDirectory(
            prefix="paper-knowledge-base-docling-"
        ) as output:
            output_path = Path(output)
            command = self._command(path, output_path, ocr=ocr)
            try:
                completed = self._runner(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
            except FileNotFoundError as exc:
                raise DoclingUnavailableError(
                    f"Docling executable was not found: {self.executable}"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise DoclingProcessError(
                    f"Docling timed out after {self.timeout_seconds} seconds"
                ) from exc
            except OSError as exc:
                raise DoclingUnavailableError(
                    f"Docling could not start: {exc}"
                ) from exc

            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                message = f"Docling exited with status {completed.returncode}"
                if detail:
                    message = f"{message}: {detail}"
                raise DoclingProcessError(message)

            json_path = self._output_file(output_path, path, ".json")
            markdown_path = self._output_file(output_path, path, ".md")
            try:
                raw_document = json.loads(json_path.read_text(encoding="utf-8"))
                markdown = markdown_path.read_text(encoding="utf-8")
            except (OSError, json.JSONDecodeError) as exc:
                raise DoclingOutputError(
                    "Docling did not produce readable JSON and Markdown output"
                ) from exc

        return DoclingParseOutput(
            document=normalize_docling_document(raw_document, markdown, ocr_used=ocr),
            raw_document=raw_document,
        )

    def _command(self, path: Path, output: Path, *, ocr: bool) -> list[str]:
        command = [
            self.executable,
            "convert",
            str(path),
            "--to",
            "md",
            "--to",
            "json",
            "--output",
            str(output),
            "--device",
            self.device,
        ]
        command.append("--ocr" if ocr else "--no-ocr")
        return command

    @staticmethod
    def _output_file(output: Path, input_path: Path, suffix: str) -> Path:
        expected = output / f"{input_path.stem}{suffix}"
        if expected.is_file():
            return expected
        matches = sorted(output.glob(f"*{suffix}"))
        if len(matches) == 1:
            return matches[0]
        raise DoclingOutputError(f"Docling output is missing a single {suffix} file")


def normalize_docling_document(
    raw_document: dict[str, Any],
    markdown: str,
    *,
    ocr_used: bool,
) -> DocumentContent:
    """Preserve declared Docling structure without inventing scholarly metadata."""

    text_values = [
        str(item["text"])
        for item in raw_document.get("texts", [])
        if isinstance(item, dict) and item.get("text")
    ]
    return DocumentContent(
        markdown=markdown,
        text="\n\n".join(text_values) or None,
        structured=raw_document,
        ocr_used=ocr_used,
        source="docling",
    )


def timed_parse(
    adapter: DoclingAdapter,
    path: Path,
    *,
    ocr: bool,
) -> tuple[DoclingParseOutput, float]:
    started = time.monotonic()
    return adapter.parse(path, ocr=ocr), time.monotonic() - started
