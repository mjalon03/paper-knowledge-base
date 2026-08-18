# Canonical paper-content quality

`improve_content_quality(content)` is a deterministic, parser-independent pass
over `PaperContent`. It returns a `ContentQualityResult` containing both the
original object (`source_content`) and a cleaned copy (`content`). The original
payload is never mutated and block/section IDs are preserved.

```python
from paper_knowledge_base.content import improve_content_quality

quality = improve_content_quality(raw_content)
mobile_content = quality.content.to_dict()
quality_json = quality.to_json()
```

## What is changed

The pass is deliberately conservative and does not use an LLM, VLM, embeddings,
or parser-native objects.

- Section headings with leading dot hierarchy markers are normalized. Strongly
  parser-like code headings and generic `Body`/`Figure`/`Table` wrappers have
  their heading hidden while their blocks remain in reading order.
- Empty metadata/asset wrappers are removed. Adjacent duplicate section wrappers
  are merged; distant sections with the same title are not merged.
- Identical page-edge paragraphs repeated across pages are treated as probable
  headers/footers. Same-page paragraph duplicates require matching geometry and
  no citation IDs before the later block is suppressed.
- Small, uncaptioned repeated or page-edge pictures are assessed as likely
  decorative noise and suppressed. Larger or otherwise uncertain pictures are
  retained and reported as `unknown`; a caption is never invented.
- A unique, same-page nearby paragraph matching a figure/table label can be
  associated as a proximity caption. Ambiguous candidates remain untouched.
- Citation references, block links, offsets, hierarchy jumps, and missing source
  locations produce typed warnings rather than silent repair.

Every suppression or presentation change is represented by a typed
`ContentTransformation` with confidence and evidence. `ContentWarning` records
uncertainty and provenance. `FigureAssessment` and `CaptionAssociation` make
picture decisions and caption sources inspectable. `ContentQualityMetrics`
contains before/after counts, suppression counts, citation resolution rate, and
source-location coverage.

## Renderer contract

The mobile renderer consumes only `quality.content` plus canonical metadata. It
does not perform another cleanup pass. Sections with
`special="quality_hidden_heading"` or an empty title render their blocks without
an empty heading. See [mobile-article-renderer.md](mobile-article-renderer.md)
for the presentation model, responsive HTML, debug mode, and asset strategy.

## Validation policy

Quality processing is validated with synthetic cases for each rule and with the
saved canonical parser outputs for the Gorzo, Reising, and Wu papers. Before/after
counts, warning codes, transformation evidence, serialized JSON, and 390px HTML
previews are checked. Parser limitations and uncertain scientific figures remain
visible in diagnostics instead of being presented as confirmed semantic facts.
