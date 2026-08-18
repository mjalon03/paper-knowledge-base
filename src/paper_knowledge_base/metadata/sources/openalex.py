"""OpenAlex REST API adapter for DOI verification and title search."""

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

DEFAULT_BASE_URL = "https://api.openalex.org"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_USER_AGENT = "paper-knowledge-base/0.1 (metadata resolution)"


class OpenAlexClient:
    """Use OpenAlex public work lookup/search with optional ``mailto`` identification."""

    source = "openalex"

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
            mailto if mailto is not None else os.environ.get("OPENALEX_MAILTO")
        )
        self._http = JsonHttpClient(
            timeout_seconds=timeout_seconds
            or float(os.environ.get("OPENALEX_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
            user_agent=user_agent
            or os.environ.get("METADATA_USER_AGENT", DEFAULT_USER_AGENT),
            opener=opener,
            sleeper=sleeper,
        )

    def lookup_doi(self, doi: str) -> SourceRecord | None:
        normalized = normalize_doi(doi)
        if not normalized:
            return None
        identifier = quote(f"https://doi.org/{normalized}", safe=":/")
        try:
            return _record(self._http.get_json(self._url(f"/works/{identifier}", {})))
        except MetadataSourceNotFoundError:
            return None

    def search(
        self, title: str, *, year: int | None = None
    ) -> tuple[SourceRecord, ...]:
        params: dict[str, str | int] = {"search": title, "per-page": 5}
        if year is not None:
            params["filter"] = f"publication_year:{year}"
        payload = self._http.get_json(self._url("/works", params))
        results = payload.get("results", [])
        return tuple(_record(item) for item in results if isinstance(item, dict))

    def _url(self, path: str, params: dict[str, str | int]) -> str:
        values = dict(params)
        if self.mailto:
            values["mailto"] = self.mailto
        query = urlencode(values)
        return f"{self.base_url}{path}{'?' + query if query else ''}"


def _record(raw: dict[str, Any]) -> SourceRecord:
    primary_location = raw.get("primary_location") or {}
    source = primary_location.get("source") or {}
    return SourceRecord(
        source="openalex",
        source_id=str(raw.get("id") or "unknown"),
        doi=normalize_doi(raw.get("doi")),
        title=raw.get("display_name"),
        authors=tuple(
            SourceAuthor(
                display_name=str(
                    (authorship.get("author") or {}).get("display_name") or ""
                ),
            )
            for authorship in raw.get("authorships", [])
            if isinstance(authorship, dict)
            and (authorship.get("author") or {}).get("display_name")
        ),
        year=raw.get("publication_year")
        if isinstance(raw.get("publication_year"), int)
        else None,
        venue=source.get("display_name"),
        publisher=source.get("host_organization_name"),
        volume=raw.get("biblio", {}).get("volume"),
        issue=raw.get("biblio", {}).get("issue"),
        pages=raw.get("biblio", {}).get("first_page"),
        work_type=raw.get("type"),
        identifiers={"openalex": str(raw.get("id") or "")},
        raw=raw,
    )
