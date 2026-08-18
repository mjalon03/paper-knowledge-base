# Paper identity and document deduplication

The identity layer keeps a concrete PDF separate from the scholarly work it
may represent:

```text
Document (PDF, filename, SHA-256)
        |
        +-- IdentityMetadata (title, authors, DOI, year, venue, type)
        |
        +-- IdentityDecision (relationship, confidence, evidence)
```

Two files can therefore be `SAME_PAPER` while remaining two Documents. An
identical SHA-256 is instead `EXACT_FILE_DUPLICATE`; a filename by itself is
never enough to make an identity decision.

## Matching hierarchy

`compare_identity()` applies evidence in this order:

1. Equal SHA-256 returns high-confidence `EXACT_FILE_DUPLICATE` immediately.
2. Equal normalized DOI returns high-confidence `SAME_PAPER`.
3. Equal OpenAlex/PMID-style external identifiers return high-confidence
   `SAME_PAPER`.
4. Explicit correction, retraction, or supplement markers are matched to a
   sufficiently similar parent and return the corresponding related-material
   relationship.
5. Preprint/accepted-manuscript and published/conference pairs with strong
   title-author-year evidence return `RELATED_VERSION`.
6. DOI-less candidates use the existing conservative title and author
   normalization plus compatible years. Numeric scores are comparison scores,
   not calibrated probabilities.

Different DOIs are evidence against `SAME_PAPER`, but are not an automatic
`DISTINCT`: they are common for preprint/published pairs and related material.
When the evidence does not meet a safe rule, the result is `AMBIGUOUS`.
False-positive merges are more harmful than unresolved duplicates, so the
automatic thresholds intentionally favor review over aggressive merging.

Every decision exposes `IdentityEvidence` records, human-readable reasons,
conflicts, comparison scores, and the provenance carried by the input
metadata. The layer performs no network access, LLM inference, embeddings, or
database persistence.

## Future storage shape

The next storage feature should keep these entities separate:

```text
Paper
  canonical scholarly work

Document
  one uploaded/downloaded/OCR PDF and its SHA-256

PaperDocument
  Document -> Paper membership, with source/provenance metadata

PaperRelation
  version-of, correction-of, retraction-of, or supplement-of
```

`SAME_PAPER` can attach a new Document to an existing Paper. `RELATED_VERSION`
and the related-material relationships should create explicit PaperRelation
rows rather than silently collapsing records. `AMBIGUOUS` should remain
reviewable and must not be auto-merged.
