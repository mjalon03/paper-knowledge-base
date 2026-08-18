"""Conservative deterministic normalization and comparison for metadata matching."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
DOI_SUFFIX_PUNCTUATION = ".,;:!?)]}"
TITLE_TERMINAL_PUNCTUATION = ".!?"
TITLE_PUNCTUATION = re.compile(r'[,:;!?"]')
AUTHOR_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_doi(value: str | None) -> str | None:
    """Normalize DOI presentation without changing its semantic identifier."""

    if not value:
        return None
    normalized = (
        DOI_PREFIX.sub("", value.strip()).strip().rstrip(DOI_SUFFIX_PUNCTUATION)
    )
    if (
        not normalized
        or not normalized.casefold().startswith("10.")
        or "/" not in normalized
    ):
        return None
    return normalized.casefold()


def normalize_title(value: str | None) -> str:
    """Produce a comparison key while preserving the caller's display title."""

    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = normalized.replace("–", "-").replace("—", "-").replace("‐", "-")
    normalized = TITLE_PUNCTUATION.sub(" ", normalized).rstrip(
        TITLE_TERMINAL_PUNCTUATION
    )
    return " ".join(normalized.split())


def normalize_author_name(value: str | None) -> str:
    """Produce a conservative comparison key without assuming name order."""

    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(AUTHOR_PUNCTUATION.sub(" ", normalized).split())


def title_similarity(left: str | None, right: str | None) -> float:
    """Blend sequence and token overlap; this is a transparent score, not probability."""

    left_key = normalize_title(left)
    right_key = normalize_title(right)
    if not left_key or not right_key:
        return 0.0
    sequence = SequenceMatcher(None, left_key, right_key).ratio()
    left_tokens = set(left_key.split())
    right_tokens = set(right_key.split())
    token_overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return 0.7 * sequence + 0.3 * token_overlap


def author_overlap(left: Sequence[str], right: Sequence[str]) -> float:
    """Return the proportion of left names with a conservative match in right names."""

    if not left or not right:
        return 0.0
    matches = sum(any(_authors_match(name, other) for other in right) for name in left)
    return matches / len(left)


def _authors_match(left: str, right: str) -> bool:
    left_key = normalize_author_name(left)
    right_key = normalize_author_name(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    left_tokens = left_key.split()
    right_tokens = right_key.split()
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return False
    # This fallback intentionally requires two signals and never reorders names.
    return left_tokens[-1] == right_tokens[-1] and any(
        left_token[0] == right_token[0]
        for left_token in left_tokens[:-1]
        for right_token in right_tokens[:-1]
        if left_token and right_token
    )
