"""Conservative text and identifier helpers for the content layer."""

from __future__ import annotations

import re
import unicodedata


def normalize_text(value: object) -> str:
    """Normalize whitespace while retaining scientific Unicode characters."""

    text = unicodedata.normalize("NFC", str(value))
    return " ".join(text.split())


def normalize_key(value: str) -> str:
    return normalize_text(value).casefold()


def split_heading(value: str) -> tuple[str | None, str]:
    """Separate an optional numeric section label without guessing semantics."""

    match = re.match(r"^((?:\d+\.)*\d+)[\s:.-]+(.+)$", normalize_text(value))
    if not match:
        return None, normalize_text(value)
    return match.group(1), match.group(2).strip()


def find_reliable_span(
    text: str, display: str, *, cursor: int = 0
) -> tuple[int, int] | None:
    """Find an exact normalized callout span; return None when it is ambiguous."""

    display = normalize_text(display)
    if not display:
        return None
    first = text.find(display, cursor)
    if first < 0:
        return None
    second = text.find(display, first + 1)
    if second >= 0:
        return None
    return first, first + len(display)


def stable_id(prefix: str, index: int) -> str:
    return f"{prefix}-{index:04d}"
