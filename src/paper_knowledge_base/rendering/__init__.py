"""Mobile-oriented HTML rendering for canonical paper content."""

from paper_knowledge_base.rendering.article import build_mobile_article
from paper_knowledge_base.rendering.html import RenderOptions, render_article_html
from paper_knowledge_base.rendering.models import (
    ArticleHeader,
    ArticleNavigationItem,
    ArticleSection,
    AssetReference,
    AssetResolver,
    MobileArticle,
)


def render_mobile_article(
    metadata,
    content,
    *,
    figure_resolver=None,
    original_pdf_url=None,
    debug=False,
    toc_max_depth=2,
    options: RenderOptions | None = None,
) -> str:
    """Build and serialize a mobile article from canonical project models."""

    article = build_mobile_article(
        metadata,
        content,
        figure_resolver=figure_resolver,
        original_pdf_url=original_pdf_url,
        debug=debug,
        toc_max_depth=toc_max_depth,
    )
    return render_article_html(article, options=options)


__all__ = [
    "ArticleHeader",
    "ArticleNavigationItem",
    "ArticleSection",
    "AssetReference",
    "AssetResolver",
    "MobileArticle",
    "RenderOptions",
    "build_mobile_article",
    "render_article_html",
    "render_mobile_article",
]
