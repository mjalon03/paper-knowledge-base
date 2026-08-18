"""Deterministic, escaped HTML serialization for mobile article views."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass

from paper_knowledge_base.content.models import (
    ContentBlock,
    Equation,
    Figure,
    Paragraph,
    Reference,
    Table,
)
from paper_knowledge_base.rendering.models import (
    ArticleNavigationItem,
    ArticleSection,
    AssetReference,
    MobileArticle,
)


@dataclass(frozen=True, kw_only=True)
class RenderOptions:
    """Presentation switches that do not belong to canonical content."""

    include_source_metadata: bool = True


def render_article_html(
    article: MobileArticle,
    *,
    options: RenderOptions | None = None,
) -> str:
    """Serialize a presentation model to a complete standalone HTML document."""

    options = options or RenderOptions()
    references = tuple(article.references)
    reference_anchors = _reference_anchors(references)
    body: list[str] = [
        '<a class="skip-link" href="#article-content">Skip to article</a>',
        _render_header(article),
    ]
    if article.abstract_blocks:
        body.append(
            '<section id="abstract" class="abstract" aria-labelledby="abstract-heading">'
            '<h2 id="abstract-heading">Abstract</h2>'
            + "".join(
                _render_block(
                    block,
                    article,
                    reference_anchors,
                    options=options,
                )
                for block in article.abstract_blocks
            )
            + "</section>"
        )
    if article.navigation:
        body.append(_render_navigation(article.navigation))
    body.append('<main id="article-content">')
    for section in article.sections:
        body.append(
            _render_section(
                section,
                article,
                reference_anchors,
                options=options,
            )
        )
    if article.standalone_blocks:
        body.append(
            '<section class="standalone-content" aria-label="Additional content">'
            + "".join(
                _render_block(
                    block,
                    article,
                    reference_anchors,
                    options=options,
                )
                for block in article.standalone_blocks
            )
            + "</section>"
        )
    body.append("</main>")
    if references:
        body.append(_render_references(references, reference_anchors))
    if article.debug:
        body.append(_render_diagnostics(article))
    body.append("</article>")
    return _document_shell("".join(body), article.header.title)


def _document_shell(body: str, title: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_escape(title)}</title><style>{CSS}</style></head>"
        f"<body><article>{body}"
        "</body></html>"
    )


def _render_header(article: MobileArticle) -> str:
    header = article.header
    author_markup = _render_authors(header.authors)
    byline = (
        f'<p class="venue">{_escape(header.venue)}'
        + (f" · {_escape(str(header.year))}" if header.year is not None else "")
        + "</p>"
        if header.venue or header.year is not None
        else ""
    )
    publisher = (
        f'<p class="publisher">{_escape(header.publisher)}</p>'
        if header.publisher
        else ""
    )
    doi = ""
    if header.doi:
        doi_href = _safe_href(f"https://doi.org/{header.doi}")
        doi = (
            f'<p class="doi">DOI: <a href="{_escape(doi_href, attribute=True)}">'
            f"{_escape(header.doi)}</a></p>"
            if doi_href
            else f'<p class="doi">DOI: {_escape(header.doi)}</p>'
        )
    pdf_action = ""
    if header.original_pdf_url:
        href = _safe_href(header.original_pdf_url)
        if href:
            pdf_action = (
                f'<p><a class="pdf-action" href="{_escape(href, attribute=True)}">'
                "View original PDF</a></p>"
            )
    return (
        "<header>"
        f'<h1 id="paper-title">{_escape(header.title)}</h1>'
        f"{author_markup}{byline}{publisher}{doi}{pdf_action}"
        "</header>"
    )


def _render_authors(authors: tuple[str, ...]) -> str:
    if not authors:
        return ""
    visible = authors[:3]
    text = " · ".join(_escape(author) for author in visible)
    if len(authors) > 3:
        text += ", et al."
        full = "".join(f"<li>{_escape(author)}</li>" for author in authors)
        return (
            f'<p class="authors">{text}</p><details class="author-list">'
            "<summary>Full author list</summary><ul>"
            f"{full}</ul></details>"
        )
    return f'<p class="authors">{text}</p>'


def _render_navigation(items: tuple[ArticleNavigationItem, ...]) -> str:
    return (
        '<nav class="contents" aria-labelledby="contents-heading">'
        '<details open><summary id="contents-heading">Contents</summary>'
        f"{_render_navigation_list(items)}</details></nav>"
    )


def _render_navigation_list(items: tuple[ArticleNavigationItem, ...]) -> str:
    if not items:
        return ""
    return (
        "<ol>"
        + "".join(
            f'<li><a href="#{_escape(item.anchor, attribute=True)}">{_escape(item.title)}</a>'
            + _render_navigation_list(item.children)
            + "</li>"
            for item in items
        )
        + "</ol>"
    )


def _render_section(
    section: ArticleSection,
    article: MobileArticle,
    reference_anchors: dict[str, str],
    *,
    options: RenderOptions,
) -> str:
    heading = (
        f"<h{section.html_level}>{_escape(section.title)}</h{section.html_level}>"
        if section.title
        else ""
    )
    attrs = (
        _source_attributes(section.source_location)
        if options.include_source_metadata
        else ""
    )
    return (
        f'<section id="{_escape(section.anchor, attribute=True)}"{attrs}>'
        f"{heading}"
        + "".join(
            _render_block(
                block,
                article,
                reference_anchors,
                options=options,
            )
            for block in section.blocks
        )
        + "</section>"
    )


def _render_block(
    block: ContentBlock,
    article: MobileArticle,
    reference_anchors: dict[str, str],
    *,
    options: RenderOptions,
) -> str:
    source_attrs = (
        _source_attributes(block.source_location)
        if options.include_source_metadata
        else ""
    )
    source_link = _render_source_link(block, article, options=options)
    if isinstance(block, Paragraph):
        return (
            f"<p{source_attrs}>"
            + _render_paragraph_text(block, article.citations, reference_anchors)
            + source_link
            + "</p>"
        )
    if isinstance(block, Figure):
        return _render_figure(block, article, source_attrs, source_link)
    if isinstance(block, Table):
        return _render_table(block, source_attrs, source_link)
    if isinstance(block, Equation):
        expression = block.latex or block.text or ""
        return (
            f'<div class="equation"{source_attrs}>'
            f"<code>{_escape(expression)}</code>{source_link}</div>"
        )
    return ""


def _render_paragraph_text(
    block: Paragraph,
    citations: tuple[object, ...],
    reference_anchors: dict[str, str],
) -> str:
    citations_by_id = {
        citation.id: citation
        for citation in citations
        if getattr(citation, "block_id", None) == block.id
        or citation.id in block.citation_ids
    }
    candidates = []
    for citation in citations_by_id.values():
        if citation.start is None or citation.end is None:
            continue
        if not 0 <= citation.start < citation.end <= len(block.text):
            continue
        targets = tuple(
            reference_anchors[reference_id]
            for reference_id in citation.reference_ids
            if reference_id in reference_anchors
        )
        if not targets or block.text[citation.start : citation.end] != citation.display:
            continue
        candidates.append((citation.start, citation.end, citation.display, targets))
    candidates.sort(key=lambda item: (item[0], item[1]))
    pieces: list[str] = []
    cursor = 0
    for start, end, display, targets in candidates:
        if start < cursor:
            continue
        pieces.append(_escape(block.text[cursor:start]))
        pieces.append(_citation_markup(display, targets))
        cursor = end
    pieces.append(_escape(block.text[cursor:]))
    return "".join(pieces)


def _citation_markup(display: str, targets: tuple[str, ...]) -> str:
    first, *additional = targets
    markup = (
        f'<span class="citation-group"><a href="#{_escape(first, attribute=True)}">'
        f"{_escape(display)}</a>"
    )
    for target in additional:
        markup += (
            f'<a class="citation-more" href="#{_escape(target, attribute=True)}" '
            'aria-label="Additional cited reference">+</a>'
        )
    return markup + "</span>"


def _render_figure(
    block: Figure,
    article: MobileArticle,
    source_attrs: str,
    source_link: str,
) -> str:
    figure_id = f"figure-{_slug(block.id) or 'item'}"
    label = block.label or "Figure"
    caption = block.caption or ""
    image = ""
    asset = _resolve_asset(block.asset_ref, article)
    if asset is not None:
        alt = asset.alt_text or caption or label
        image = (
            f'<img src="{_escape(asset.href, attribute=True)}" alt="{_escape(alt, attribute=True)}" '
            'loading="lazy">'
        )
    else:
        image = (
            '<div class="figure-fallback">Image unavailable in current extraction</div>'
        )
    return (
        f'<figure id="{_escape(figure_id, attribute=True)}"{source_attrs}>'
        f'<div class="figure-label">{_escape(label)}</div>{image}'
        f"<figcaption>{_escape(caption)}{source_link}</figcaption></figure>"
    )


def _resolve_asset(
    asset_ref: str | None, article: MobileArticle
) -> AssetReference | None:
    if not asset_ref or article.figure_resolver is None:
        return None
    try:
        resolver = article.figure_resolver
        resolved = (
            resolver.get(asset_ref) if hasattr(resolver, "get") else resolver(asset_ref)
        )
    except Exception:  # noqa: BLE001 - an optional resolver must never break reading
        return None
    if isinstance(resolved, AssetReference):
        return resolved if _safe_href(resolved.href, image=True) else None
    if isinstance(resolved, str):
        href = _safe_href(resolved, image=True)
        return AssetReference(identifier=asset_ref, href=href) if href else None
    return None


def _render_table(block: Table, source_attrs: str, source_link: str) -> str:
    label = block.label or "Table"
    caption = block.caption or ""
    if not block.headers and not block.rows:
        content = f'<pre class="table-text">{_escape(block.plain_text or "")}</pre>'
    else:
        head = (
            "<thead><tr>"
            + "".join(
                f'<th scope="col">{_escape(value)}</th>' for value in block.headers
            )
            + "</tr></thead>"
            if block.headers
            else ""
        )
        rows = "".join(
            "<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>"
            for row in block.rows
        )
        content = f'<div class="table-scroll"><table>{head}<tbody>{rows}</tbody></table></div>'
    return (
        f'<figure class="table-figure"{source_attrs}>'
        f'<div class="figure-label">{_escape(label)}</div>{content}'
        f"<figcaption>{_escape(caption)}{source_link}</figcaption></figure>"
    )


def _render_references(
    references: tuple[Reference, ...],
    reference_anchors: dict[str, str],
) -> str:
    items: list[str] = []
    for reference in references:
        label = f"{reference.label} " if reference.label else ""
        details = []
        if reference.title:
            details.append(reference.title)
        if reference.authors:
            details.append(", ".join(reference.authors))
        if reference.venue:
            details.append(reference.venue)
        if reference.year is not None:
            details.append(str(reference.year))
        detail_text = ". ".join(details) or reference.raw_text
        doi = ""
        if reference.doi:
            href = _safe_href(f"https://doi.org/{reference.doi}")
            if href:
                doi = (
                    f' <a class="reference-doi" href="{_escape(href, attribute=True)}">'
                    "DOI</a>"
                )
        items.append(
            f'<li id="{_escape(reference_anchors[reference.id], attribute=True)}">'
            f'<span class="reference-label">{_escape(label)}</span>'
            f"{_escape(detail_text)}{doi}</li>"
        )
    return (
        '<section id="references"><h2>References</h2><ol>'
        + "".join(items)
        + "</ol></section>"
    )


def _render_diagnostics(article: MobileArticle) -> str:
    if not article.diagnostics:
        return (
            '<aside class="diagnostics"><h2>Diagnostics</h2><p>No warnings.</p></aside>'
        )
    items = "".join(f"<li>{_escape(item)}</li>" for item in article.diagnostics)
    return f'<aside class="diagnostics"><h2>Diagnostics</h2><ul>{items}</ul></aside>'


def _render_source_link(
    block: ContentBlock,
    article: MobileArticle,
    *,
    options: RenderOptions,
) -> str:
    if (
        not article.debug
        or not options.include_source_metadata
        or block.source_location is None
    ):
        return ""
    page = block.source_location.page_number
    if page is None:
        return ""
    if article.header.original_pdf_url:
        href = _safe_href(article.header.original_pdf_url)
        if href:
            return (
                f' <a class="source-link" href="{_escape(href + "#page=" + str(page), attribute=True)}">'
                f"Original PDF · page {page}</a>"
            )
    return f' <span class="source-link">Original PDF · page {page}</span>'


def _source_attributes(location: object) -> str:
    page = getattr(location, "page_number", None)
    bbox = getattr(location, "bbox", None)
    attrs = []
    if isinstance(page, int):
        attrs.append(f' data-source-page="{page}"')
    if bbox is not None:
        values = (bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        attrs.append(
            f' data-source-bbox="{_escape(",".join(str(value) for value in values), attribute=True)}"'
        )
    return "".join(attrs)


def _reference_anchor(reference_id: str) -> str:
    return f"ref-{_slug(reference_id) or 'reference'}"


def _reference_anchors(references: tuple[Reference, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    used: set[str] = set()
    for reference in references:
        anchor = _reference_anchor(reference.id)
        if anchor in used:
            anchor = f"{anchor}-{_slug(reference.id)[-8:] or 'item'}"
        while anchor in used:
            anchor += "-x"
        result[reference.id] = anchor
        used.add(anchor)
    return result


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()[:100]


def _escape(value: object, *, attribute: bool = False) -> str:
    return html_lib.escape(str(value), quote=attribute)


def _safe_href(value: str, *, image: bool = False) -> str | None:
    candidate = value.strip()
    lowered = candidate.casefold()
    if lowered.startswith(("javascript:", "vbscript:", "file:")):
        return None
    if image and lowered.startswith("data:") and not lowered.startswith("data:image/"):
        return None
    if lowered.startswith("data:") and not image:
        return None
    if image and lowered.startswith("data:image/"):
        return candidate
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate):
        return candidate if lowered.startswith(("https://", "http://")) else None
    if image and candidate.startswith("/"):
        return None
    if candidate.startswith(("/", "./", "../", "#")):
        return candidate
    if re.match(r"^[a-zA-Z0-9._-]+/", candidate):
        return candidate
    return None


CSS = """
:root { color-scheme: light dark; font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; }
* { box-sizing: border-box; }
body { margin: 0; background: #f3f5f7; color: #1d232a; }
article { width: min(100%, 860px); margin: 0 auto; padding: 1rem; background: #fff; }
header { padding: .5rem 0 1.25rem; border-bottom: 1px solid #d8dde3; }
h1 { margin: 0 0 .75rem; font-size: clamp(1.65rem, 5vw, 2.5rem); line-height: 1.15; }
h2, h3, h4, h5, h6 { line-height: 1.25; margin-top: 1.75rem; }
.authors, .venue, .publisher, .doi { margin: .35rem 0; overflow-wrap: anywhere; }
.authors { font-weight: 600; }
.publisher, .doi, figcaption, .source-link { color: #5b6672; font-size: .92rem; }
a { color: #075a9a; overflow-wrap: anywhere; }
p { max-width: 72ch; margin: 1rem 0; }
.abstract, .contents, .diagnostics { margin: 1.25rem 0; padding: .9rem 1rem; border: 1px solid #d8dde3; border-radius: .5rem; }
.abstract p { margin-bottom: .35rem; }
.contents summary, .author-list summary { cursor: pointer; font-weight: 700; }
.contents ol { margin: .5rem 0 0; padding-left: 1.3rem; }
.contents li { margin: .25rem 0; }
section { scroll-margin-top: 1rem; }
figure { margin: 1.5rem 0; max-width: 100%; }
figure img { display: block; max-width: 100%; height: auto; margin: .5rem auto; }
.figure-label { font-weight: 700; }
figcaption { margin-top: .5rem; overflow-wrap: anywhere; }
.figure-fallback { padding: 2rem 1rem; text-align: center; background: #eef1f4; color: #5b6672; }
.table-scroll { max-width: 100%; overflow-x: auto; overscroll-behavior-x: contain; }
table { min-width: 100%; border-collapse: collapse; }
th, td { border: 1px solid #b8c0c8; padding: .45rem .6rem; text-align: left; vertical-align: top; }
th { background: #eef1f4; }
.table-text { max-width: 100%; overflow-x: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.equation { max-width: 100%; padding: .75rem; overflow-x: auto; background: #f5f6f8; }
.equation code { white-space: pre-wrap; overflow-wrap: anywhere; }
.citation-more { margin-left: .2rem; font-size: .8em; }
.reference-label { font-weight: 700; }
#references li { margin: .75rem 0; overflow-wrap: anywhere; }
.diagnostics { background: #fff8e1; }
.skip-link { position: absolute; left: -9999px; }
.skip-link:focus { left: 1rem; top: 1rem; z-index: 1; padding: .5rem; background: #fff; }
@media (min-width: 700px) { article { padding: 2rem 3rem; } }
@media (prefers-color-scheme: dark) { body { background: #16191d; color: #e8edf2; } article { background: #20252b; } a { color: #83c9ff; } .abstract, .contents, .diagnostics, .figure-fallback, .equation, th { background: #2b323a; } th, td { border-color: #68727d; } }
"""
