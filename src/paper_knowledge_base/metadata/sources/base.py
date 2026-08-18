"""Small stdlib HTTP primitives shared by public metadata-source clients."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MetadataSourceError(Exception):
    """Base exception for a public metadata-source request."""


class MetadataSourceUnavailableError(MetadataSourceError):
    """A metadata service could not be reached or returned a transient failure."""


class MetadataSourceResponseError(MetadataSourceError):
    """A metadata service returned malformed or non-successful content."""


class MetadataSourceNotFoundError(MetadataSourceResponseError):
    """A metadata service has no record for the requested identifier."""


Opener = Callable[[Request, float], object]
Sleeper = Callable[[float], None]


class JsonHttpClient:
    """Bounded GET JSON client with one retry for rate-limits and server failures."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        user_agent: str,
        opener: Opener | None = None,
        sleeper: Sleeper | None = None,
        max_retries: int = 1,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._opener = opener or _open_request
        self._sleeper = sleeper or time.sleep
        self.max_retries = max_retries

    def get_json(self, url: str) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            request = Request(url, headers={"User-Agent": self.user_agent})
            try:
                with self._opener(request, self.timeout_seconds) as response:
                    payload = response.read().decode("utf-8")
                decoded = json.loads(payload)
                if not isinstance(decoded, dict):
                    raise MetadataSourceResponseError("Expected a JSON object response")
                return decoded
            except HTTPError as exc:
                if exc.code == 404:
                    raise MetadataSourceNotFoundError("Record not found") from exc
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    self._sleeper(_retry_after_seconds(exc))
                    continue
                detail = exc.read().decode("utf-8", errors="replace").strip()
                message = f"HTTP {exc.code}"
                if detail:
                    message = f"{message}: {detail}"
                raise MetadataSourceResponseError(message) from exc
            except (URLError, OSError, TimeoutError) as exc:
                raise MetadataSourceUnavailableError(f"Request failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise MetadataSourceResponseError("Invalid JSON response") from exc
        raise MetadataSourceUnavailableError("Retry budget exhausted")


def _retry_after_seconds(error: HTTPError) -> float:
    header = error.headers.get("Retry-After") if error.headers else None
    try:
        return min(float(header), 10.0) if header else 1.0
    except ValueError:
        return 1.0


def _open_request(request: Request, timeout: float) -> object:
    return urlopen(request, timeout=timeout)
