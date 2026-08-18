# Mobile article renderer

The renderer turns canonical project-owned paper data into a readable,
single-column HTML article for local UX validation. It is not a PDF viewer and
does not know about GROBID, Docling, parser output, or content-cleanup rules.

```text
PDF
 ↓
Processing
 ↓
Canonical Metadata + Canonical PaperContent
 ↓
Content Quality
 ↓
Mobile-ready PaperContent
 ↓
paper_knowledge_base.rendering
 ↓
Responsive HTML
```

## Boundary and presentation model

`rendering.article.build_mobile_article()` accepts `CanonicalPaperMetadata` and
either `PaperContent` or `ContentQualityResult`. When a quality result is
provided, only its cleaned `.content` is rendered. The adapter creates the
renderer-owned `MobileArticle`, `ArticleHeader`, `ArticleSection`, and
`ArticleNavigationItem` view models. `rendering.html.render_article_html()` is
the only HTML serializer.

Canonical JSON is unchanged. The compatibility script rehydrates that
project-owned JSON shape and delegates to the same renderer:

```bash
uv run python scripts/render_mobile_article.py content.json preview.html
uv run python scripts/render_mobile_article.py content.json preview.html --debug
```

The script remains useful for existing serialized fixtures; new callers should
use `paper_knowledge_base.rendering.render_mobile_article()` with domain models.

## Article behavior

- The header renders title, a compact author list, venue/year, publisher, DOI,
  and an optional original-PDF URL. More than three authors are shortened to
  `et al.` while a details element retains the full list.
- The canonical paragraph marked `metadata_field="scholarly.abstract"` (or the
  canonical Abstract section) is rendered once near the top. Abstract sections
  are omitted from the ordinary body stream, so the renderer does not duplicate
  the derived abstract.
- Section anchors are deterministic and derived from canonical section IDs.
  Headings are normalized to h2 and below from the canonical parent hierarchy;
  parser numeric levels do not create skipped heading levels.
- The Contents navigation defaults to two visible hierarchy levels. Deeper
  sections remain in the article and keep their anchors.
- Paragraph text is never rewritten. Reliable canonical citation offsets become
  links to reference anchors. Invalid or unresolved citation mappings remain
  escaped plain text. Multiple resolved references retain additional links.
- Figures use an injected resolver for opaque `Figure.asset_ref` values. A
  resolver may return an `AssetReference` or safe relative/HTTP URL. Without a
  usable asset, the figure and caption remain visible with an honest fallback.
  The renderer never fabricates image data or performs another cleanup pass.
- Structured tables use semantic `table`, `thead`, `th`, and `td` elements in a
  localized horizontal-scroll container. Plain-text tables use an escaped
  preformatted fallback. Equations are escaped text/LaTeX in a responsive code
  block; a richer math renderer can be added later.

## Source links, diagnostics, and safety

Known source pages are retained as `data-source-page` (and bbox) attributes in
the generated markup. In debug mode, blocks also show an `Original PDF · page N`
action when an original-PDF URL is supplied. Normal mode does not expose source
labels or quality warnings. Debug mode shows quality warning messages, but does
not alter the cleaned content.

All text and table cells are escaped. Asset and PDF URLs reject script, file,
and unsafe schemes; absolute local figure paths are rejected by the default
asset path policy. No parser HTML is emitted. The HTML uses semantic article,
header, nav, section, figure, figcaption, table, links, and logical headings,
with a skip link and caption-derived figure alt text.

The CSS is self-contained and mobile-first. Figures use `max-width: 100%`,
tables scroll inside `.table-scroll`, long references and DOI URLs wrap, and
the article remains a single column at 390px and 430px. Generated previews,
assets, screenshots, and parser dumps remain outside version control.

## Known limitations

Canonical `Figure` objects currently contain opaque asset references rather than
image bytes or extracted files. Real extracted images therefore require a
follow-up asset bridge. Missing or uncertain captions, parser heading noise,
unresolved citations, and missing source locations remain content/parser issues;
the renderer exposes them conservatively instead of silently repairing them.
