"""HTTP adapter for GROBID full-text TEI extraction."""

from __future__ import annotations

import mimetypes
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from paper_knowledge_base.parsers.tei import extract_tei_fields
from paper_knowledge_base.processing.models import (
    Affiliation,
    Author,
    MetadataField,
    Reference,
    ScholarlyMetadata,
    Section,
)

DEFAULT_GROBID_BASE_URL = "http://127.0.0.1:8070"
DEFAULT_GROBID_TIMEOUT_SECONDS = 300.0


class GrobidError(Exception):
    """Base exception for GROBID execution and TEI normalization failures."""


class GrobidRequestError(GrobidError):
    """GROBID could not accept or process a document request."""


class GrobidResponseError(GrobidError):
    """GROBID returned malformed or unexpected TEI."""


@dataclass(frozen=True)
class GrobidParseOutput:
    scholarly: ScholarlyMetadata
    raw_tei_xml: str


def _multipart_pdf(path: Path) -> tuple[bytes, str]:
    boundary = f"----paper-knowledge-base-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
    payload = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="input"; filename="{path.name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode(),
            path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    return payload, boundary


def normalize_tei_xml(raw_tei_xml: str) -> ScholarlyMetadata:
    """Normalize explicit GROBID TEI fields without repairing candidate metadata."""

    try:
        root = ElementTree.fromstring(raw_tei_xml)
    except ElementTree.ParseError as exc:
        raise GrobidResponseError("GROBID returned invalid TEI XML") from exc

    fields = extract_tei_fields(root)
    return ScholarlyMetadata(
        title=MetadataField(fields.title, "grobid" if fields.title else None),
        authors=tuple(Author(name=name, source="grobid") for name in fields.authors),
        affiliations=tuple(
            Affiliation(name=name, source="grobid") for name in fields.affiliations
        ),
        abstract=MetadataField(
            fields.abstract,
            "grobid" if fields.abstract else None,
        ),
        doi=MetadataField(fields.doi, "grobid" if fields.doi else None),
        sections=tuple(
            Section(heading=section.heading, text=section.text, source="grobid")
            for section in fields.sections
        ),
        references=tuple(
            Reference(text=reference, source="grobid")
            for reference in fields.references
        ),
    )


class GrobidAdapter:
    """Submit PDFs to a separately managed GROBID HTTP service."""

    name = "grobid"
    version = "0.9.1"

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        *,
        opener: Callable[[Request, float], object] | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("GROBID_BASE_URL") or DEFAULT_GROBID_BASE_URL
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(
            os.environ.get("GROBID_TIMEOUT", DEFAULT_GROBID_TIMEOUT_SECONDS)
        )
        self._opener = opener or _open_request

    def parse(self, path: Path) -> GrobidParseOutput:
        payload, boundary = _multipart_pdf(path)
        request = Request(
            f"{self.base_url}/api/processFulltextDocument",
            data=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with self._opener(request, self.timeout_seconds) as response:
                raw_tei_xml = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            message = f"GROBID HTTP {exc.code}"
            if detail:
                message = f"{message}: {detail}"
            raise GrobidRequestError(message) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise GrobidRequestError(f"GROBID request failed: {exc}") from exc

        return GrobidParseOutput(
            scholarly=normalize_tei_xml(raw_tei_xml),
            raw_tei_xml=raw_tei_xml,
        )


def _open_request(request: Request, timeout: float) -> object:
    return urlopen(request, timeout=timeout)


def timed_parse(adapter: GrobidAdapter, path: Path) -> tuple[GrobidParseOutput, float]:
    """Run an adapter and expose timing to the orchestrator without policy coupling."""

    started = time.monotonic()
    return adapter.parse(path), time.monotonic() - started
