"""Presentation models for the mobile article renderer.

These types adapt canonical paper data for a reader without adding presentation
fields to :mod:`paper_knowledge_base.content`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from paper_knowledge_base.content.models import (
    Citation,
    ContentBlock,
    Reference,
    SourceLocation,
)


@dataclass(frozen=True, kw_only=True)
class AssetReference:
    """A safe, renderer-resolved reference to an extracted figure asset."""

    identifier: str
    href: str
    mime_type: str | None = None
    alt_text: str | None = None


AssetResolver = (
    Callable[[str], AssetReference | str | None]
    | Mapping[str, AssetReference | str | None]
)


@dataclass(frozen=True, kw_only=True)
class ArticleHeader:
    title: str
    authors: tuple[str, ...] = ()
    venue: str | None = None
    publisher: str | None = None
    year: int | str | None = None
    doi: str | None = None
    original_pdf_url: str | None = None


@dataclass(frozen=True, kw_only=True)
class ArticleNavigationItem:
    title: str
    anchor: str
    depth: int
    children: tuple[ArticleNavigationItem, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ArticleSection:
    section_id: str
    anchor: str
    title: str
    html_level: int
    depth: int
    blocks: tuple[ContentBlock, ...] = ()
    source_location: SourceLocation | None = None


@dataclass(frozen=True, kw_only=True)
class MobileArticle:
    """A presentation-ready article assembled from canonical domain objects."""

    header: ArticleHeader
    sections: tuple[ArticleSection, ...]
    navigation: tuple[ArticleNavigationItem, ...]
    abstract_blocks: tuple[ContentBlock, ...] = ()
    standalone_blocks: tuple[ContentBlock, ...] = ()
    references: tuple[Reference, ...] = ()
    citations: tuple[Citation, ...] = ()
    source_document_id: str | None = None
    source_document_sha256: str | None = None
    diagnostics: tuple[str, ...] = ()
    figure_resolver: AssetResolver | None = field(
        default=None, repr=False, compare=False
    )
    debug: bool = False
    toc_max_depth: int = 2
