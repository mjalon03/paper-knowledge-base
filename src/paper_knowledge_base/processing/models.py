"""In-memory, parser-independent results for paper processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ParserStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ProcessingStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ProcessingRoute(str, Enum):
    EMBEDDED_TEXT = "embedded_text"
    OCR_FALLBACK = "ocr_fallback"


@dataclass(frozen=True)
class FileInfo:
    path: Path
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class PDFInspection:
    page_count: int
    text_character_count: int
    pages_with_meaningful_text: int
    text_page_ratio: float
    average_characters_per_page: float
    has_usable_embedded_text: bool


@dataclass(frozen=True)
class MetadataField:
    value: str | None
    source: str | None


@dataclass(frozen=True)
class Author:
    name: str
    source: str


@dataclass(frozen=True)
class Affiliation:
    name: str
    source: str


@dataclass(frozen=True)
class Section:
    heading: str | None
    text: str | None
    source: str


@dataclass(frozen=True)
class Reference:
    text: str
    source: str


@dataclass(frozen=True)
class ScholarlyMetadata:
    title: MetadataField = field(default_factory=lambda: MetadataField(None, None))
    authors: tuple[Author, ...] = ()
    affiliations: tuple[Affiliation, ...] = ()
    abstract: MetadataField = field(default_factory=lambda: MetadataField(None, None))
    doi: MetadataField = field(default_factory=lambda: MetadataField(None, None))
    sections: tuple[Section, ...] = ()
    references: tuple[Reference, ...] = ()


@dataclass(frozen=True)
class DocumentContent:
    markdown: str | None = None
    text: str | None = None
    structured: dict[str, Any] | None = None
    ocr_used: bool | None = None
    source: str | None = None


@dataclass(frozen=True)
class ParserRun:
    parser: str
    status: ParserStatus
    runtime_seconds: float | None
    version: str | None
    error_type: str | None = None
    error_message: str | None = None
    raw_output: str | dict[str, Any] | None = None


@dataclass(frozen=True)
class PaperProcessingResult:
    file: FileInfo
    inspection: PDFInspection
    route: ProcessingRoute
    status: ProcessingStatus
    scholarly: ScholarlyMetadata
    document: DocumentContent
    parser_runs: dict[str, ParserRun]
