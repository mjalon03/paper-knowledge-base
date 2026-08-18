# Canonical paper content

The content feature converts parser output into a parser-independent article
representation for a future mobile, single-column reader. It is intentionally not
a PDF viewer and does not implement chunking, embeddings, search, RAG, or a web UI.

```text
PDF
  ↓
GROBID + Docling
  ↓
PaperProcessingResult
  ↓
build_paper_content()
  ↓
PaperContent
  ├── sections and hierarchy
  ├── ordered paragraphs / figures / tables / equations
  ├── references and citation links
  └── source page, bbox, and parser provenance
  ↓
future mobile article renderer
```

## Domain boundary

`src/paper_knowledge_base/content/` contains only project-owned frozen dataclasses.
The application-facing types do not import GROBID TEI classes, Docling classes, or
raw Docling JSON. The parser-specific mappers are the only modules that understand
those source formats.

`PaperContent.blocks` is the stable linear reading stream. Every block has a stable
ID, an order, an optional section ID, and provenance. `Section.block_ids` provides
the section-local view without copying the block payload. Sections carry `level`,
`label`, `title`, and `parent_id`, so a numeric label such as `2.1` is kept separate
from the display title `Imaging`.

The abstract is represented as a derived `Paragraph` in a special `Abstract`
section. Its `metadata_field` is `scholarly.abstract`; it is a rendering projection
of the existing canonical scholarly metadata, not a second independently editable
source of truth.

## Parser ownership and merge policy

GROBID owns the scholarly structure when its run succeeds:

- TEI division hierarchy and section semantics
- paragraph text and conservative citation callouts
- bibliography records and citation-to-reference IDs
- explicit figure/table/formula semantics when Docling is unavailable

Docling owns layout-rich information:

- reading order and OCR text when the OCR route is selected
- page numbers and bounding boxes
- structured table cells
- picture/caption records and opaque image asset references
- formulas when represented as typed text blocks

When both parsers succeed, GROBID paragraphs/sections/references/citations form the
semantic spine. Docling figures, tables, and equations replace the corresponding
GROBID asset types and are attached to a GROBID section only when normalized section
titles match. Unmatched assets remain standalone blocks and are still rendered. A
conservative text-prefix match may add Docling page/bbox provenance to a GROBID
paragraph; it never replaces the GROBID text.

If GROBID is missing or failed, Docling can produce a complete OCR/layout-derived
content result. If one parser fails while the other produces content, the result is
`partial` and includes a warning. No parser-native object is serialized.

## Locations, figures, tables, and equations

`SourceLocation` stores the source page, element ID, parser, coordinate system, and
optional `BoundingBox`. Coordinates are not silently converted between GROBID and
Docling. GROBID `page,x,y,width,height` values retain their raw string and are
represented as `GROBID_PDF`; Docling `l,t,r,b` values retain their declared
`coord_origin` and use a `docling-*` coordinate system.

Figure image bytes are never stored in `PaperContent`. A figure has an opaque
`asset_ref`; inline `data:` image payloads are reduced to a source-element reference.
Tables preserve headers, rows, a plain-text fallback, and parser provenance. Equation
text is preserved as supplied; LaTeX is populated only when the source explicitly
provides it.

## References and citations

References use stable `reference-####` IDs and retain raw text plus fields that GROBID
explicitly exposes: title, authors, year, venue, DOI, and source identifiers. The
feature does not enrich bibliography entries through Crossref/OpenAlex.

Citation callouts use stable IDs, display text, one or more reference IDs, and the
containing block ID. Character offsets are emitted only when the normalized display
text has one reliable occurrence in the paragraph. Otherwise the citation remains
linked by ID without fabricated offsets.

## Serialization and debug renderer

`PaperContent.to_dict()` returns only primitives, lists, dictionaries, strings,
numbers, booleans, and nulls. `to_json()` uses UTF-8, `ensure_ascii=False`, and sorted
keys for deterministic snapshots. The development-only
`scripts/render_mobile_article.py` accepts that serialized shape and emits semantic
HTML (`article`, `section`, `p`, `figure`, `table`, and references) with small
responsive CSS. It does not import or consume either parser.

Real local parser-output validation produced temporary previews for Gorzo, Reising,
and Wu. At a 390px viewport, all three previews had no horizontal overflow, rendered
references, and preserved their canonical figure/table counts. The generated HTML
and JSON remain outside the repository under `/tmp` during validation.

## Known limitations

The current benchmark outputs show parser limitations rather than universal semantic
quality. GROBID can emit noisy section headings or front-matter text for difficult
layouts: the Wu output includes an implicit `Body` section with a combined author /
highlights block, and the Reising output contains malformed-looking heading labels.
Docling can over-detect pictures, especially in Wu. Unmatched cross-parser assets
therefore remain standalone instead of being forced into an incorrect section.

These limitations are intentionally documented for a future narrow content-quality
refinement feature. This feature does not add paper-specific heading heuristics or
claim that parser output is fully adjudicated.
