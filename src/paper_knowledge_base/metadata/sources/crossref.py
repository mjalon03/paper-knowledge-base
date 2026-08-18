"""Crossref REST API adapter for DOI verification and bibliographic search."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote, urlencode

from paper_knowledge_base.metadata.models import SourceAuthor, SourceRecord
from paper_knowledge_base.metadata.normalization import normalize_doi
from paper_knowledge_base.metadata.sources.base import (
    JsonHttpClient,
    MetadataSourceNotFoundError,
    Opener,
    Sleeper,
)

DEFAULT_BASE_URL = "https://api.crossref.org"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_USER_AGENT = "paper-knowledge-base/0.1 (metadata resolution)"


class CrossrefClient:
    """Use Crossref's public REST API with optional polite-pool identification.

    Crossref documents ``/works/doi/{doi}`` for DOI retrieval and
    ``query.bibliographic`` for citation-like searches. Public access requires
    no credential; ``CROSSREF_MAILTO`` is optional and never hardcoded.
    """

    source = "crossref"

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        mailto: str | None = None,
        user_agent: str | None = None,
        *,
        opener: Opener | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.mailto = (
            mailto if mailto is not None else os.environ.get("CROSSREF_MAILTO")
        )
        self._http = JsonHttpClient(
            timeout_seconds=timeout_seconds
            or float(os.environ.get("CROSSREF_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
            user_agent=user_agent
            or os.environ.get("METADATA_USER_AGENT", DEFAULT_USER_AGENT),
            opener=opener,
            sleeper=sleeper,
        )

    def lookup_doi(self, doi: str) -> SourceRecord | None:
        normalized = normalize_doi(doi)
        if not normalized:
            return None
        try:
            payload = self._http.get_json(
                self._url(f"/works/doi/{quote(normalized, safe='/')}", {})
            )
        except MetadataSourceNotFoundError:
            return None
        message = payload.get("message")
        return _record(message) if isinstance(message, dict) else None

    def search(
        self, title: str, *, year: int | None = None
    ) -> tuple[SourceRecord, ...]:
        params: dict[str, str | int] = {"query.bibliographic": title, "rows": 5}
        if year is not None:
            params["filter"] = f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31"
        payload = self._http.get_json(self._url("/works", params))
        message = payload.get("message")
        items = message.get("items", []) if isinstance(message, dict) else []
        return tuple(_record(item) for item in items if isinstance(item, dict))

    def _url(self, path: str, params: dict[str, str | int]) -> str:
        values = dict(params)
        if self.mailto:
            values["mailto"] = self.mailto
        query = urlencode(values)
        return f"{self.base_url}{path}{'?' + query if query else ''}"


def _record(raw: dict[str, Any]) -> SourceRecord:
    title = raw.get("title")
    issued = raw.get("issued", {})
    date_parts = issued.get("date-parts", []) if isinstance(issued, dict) else []
    year = date_parts[0][0] if date_parts and date_parts[0] else None
    return SourceRecord(
        source="crossref",
        source_id=str(raw.get("DOI") or raw.get("URL") or "unknown"),
        doi=normalize_doi(raw.get("DOI")),
        title=title[0] if isinstance(title, list) and title else None,
        authors=tuple(
            SourceAuthor(
                display_name=" ".join(
                    part for part in (author.get("given"), author.get("family")) if part
                )
                or str(author.get("name") or ""),
                given_name=author.get("given"),
                family_name=author.get("family"),
            )
            for author in raw.get("author", [])
            if isinstance(author, dict)
        ),
        year=year if isinstance(year, int) else None,
        venue=(raw.get("container-title") or [None])[0],
        publisher=raw.get("publisher"),
        volume=raw.get("volume"),
        issue=raw.get("issue"),
        pages=raw.get("page"),
        work_type=raw.get("type"),
        identifiers={"crossref": str(raw.get("DOI") or raw.get("URL") or "")},
        raw=raw,
    )
