# Paper Knowledge Base

Personal research paper ingestion, processing, analysis, and knowledge management system.

## Project Goals

- Ingest research papers
- Extract structured paper content
- Detect duplicate papers and document versions
- Resolve canonical metadata
- Classify and tag papers
- Generate structured summaries
- Build semantic search and RAG capabilities
- Provide a web interface for managing the paper library

## Status

The first local processing pipeline is implemented. It combines mature parsers
instead of extending custom scholarly-PDF heuristics.

```text
PDF
  -> ingestion validation and SHA-256 fingerprint
  -> lightweight selectable-text inspection
  -> GROBID for scholarly candidate metadata (when embedded text is usable)
  -> Docling for Markdown, document structure, and OCR fallback
  -> one provenance-aware PaperProcessingResult
```

`GROBID` owns candidate scholarly semantics: title, authors, affiliations,
abstract, DOI, sections, and references. `Docling` owns document/layout output
and the current local OCR fallback. GROBID output is candidate data, not
canonical truth. Crossref and OpenAlex now provide external verification and
enrichment through a canonical metadata resolver.

```text
GROBID candidate metadata
  -> Crossref DOI lookup or bibliographic search
  -> OpenAlex DOI lookup or title search
  -> transparent deterministic evidence comparison
  -> provenance-aware canonical metadata, conflict, or unverified result
```

No source is automatically trusted. A DOI response with an incompatible title is
a conflict; a missing DOI is recovered only from a strong title/author match,
preferably when Crossref and OpenAlex independently converge. Source agreement
can replace GROBID's candidate authors while retaining those candidates as
evidence. The known Reising anomaly (six GROBID authors and no DOI) is therefore
visible, not patched by a paper-specific rule.

When equally titled records otherwise tie, the resolver gives a small,
centralized preference to a `journal-article`/`article` record over
`posted-content`/`preprint`. This chooses an external metadata record; it does
not merge versions or implement paper-identity resolution, and competing source
records remain in the returned evidence.

Paper identity and PDF deduplication are now implemented as a separate,
database-independent layer. `DocumentIdentity` models one concrete PDF and its
metadata, while `compare_identity()` returns an explainable relationship such
as `EXACT_FILE_DUPLICATE`, `SAME_PAPER`, `RELATED_VERSION`, a related-material
relationship, `DISTINCT`, or `AMBIGUOUS`. See
[docs/paper-identity.md](docs/paper-identity.md) for the matching hierarchy and
the recommended future storage model. The identity matcher is deterministic
and offline: it adds no LLM, embeddings, network, or database dependency.

Persistent storage is implemented separately under
`paper_knowledge_base.storage` with PostgreSQL as the production target,
SQLite-backed unit tests, and Alembic migrations. It preserves Paper,
Document, PaperDocument, Author/PaperAuthor, and PaperRelation as distinct
entities. See [docs/paper-storage.md](docs/paper-storage.md) for setup,
relation direction, deletion policy, and identity-to-storage behavior.

## Processing one PDF

Start a local GROBID service separately. The benchmark validated GROBID 0.9.1
at `http://127.0.0.1:8070`:

```bash
git clone --depth 1 --branch 0.9.1 https://github.com/grobidOrg/grobid.git /path/to/grobid
(cd /path/to/grobid && ./gradlew run)
```

Docling intentionally remains outside the core package dependency group: it is
large and model-backed, while most project operations do not need it. Install
it in a dedicated environment, then expose its executable. The benchmark's
isolated environment is one valid local choice.

```bash
cp .env.example .env
export GROBID_BASE_URL=http://127.0.0.1:8070
export DOCLING_EXECUTABLE=/absolute/path/to/docling
uv run python -m paper_knowledge_base.processing.pipeline data/paper.pdf --verbose
uv run python -m paper_knowledge_base.processing.pipeline data/paper.pdf --resolve-metadata --verbose
```

The command prints a concise summary. Raw GROBID TEI and Docling JSON/Markdown
are retained in the in-memory result for later persistence; the command does
not write parser output to tracked paths by default.

Routing is deliberately simple and documented in
`processing.inspection.TextCoverageThresholds`: a document needs sufficient
total selectable text, a meaningful text page, and a meaningful page-average
before GROBID is attempted. A scan skips GROBID and asks Docling to use OCR.
This is routing logic, not a claim that text coverage perfectly detects scans.

## Testing

Fast unit tests use mocked HTTP, fake parser adapters, and generated tiny PDFs;
they require neither a GROBID service nor Docling models.

```bash
uv run pytest
uv run ruff format --check .
uv run ruff check .
```

Optional local integration tests run the three ignored research PDFs through
both configured services:

```bash
PKB_RUN_INTEGRATION=1 uv run pytest -m integration
```

Metadata source tests are also opt-in and make only two public DOI requests:

```bash
PKB_RUN_METADATA_INTEGRATION=1 uv run pytest -m metadata_integration
```

The resolver uses the public [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
for `/works/doi/{doi}` lookup and `query.bibliographic` search, and the public
[OpenAlex Works API](https://api.openalex.org/) for DOI lookup and title search.
Neither requires an API key. Set `CROSSREF_MAILTO` and `OPENALEX_MAILTO` only if
you want optional polite-pool identification; `METADATA_USER_AGENT` identifies
the application without embedding a personal email. Clients have bounded
timeouts and one retry for 429/5xx responses, and failures return unverified or
partially resolved metadata rather than invalidating PDF processing.

Known limitations remain: source records can disagree, preprint and published
versions can differ, author formatting is not universal, DOI can be absent, and
an ambiguous title-only match is intentionally left unresolved. The identity
layer does not persist a duplicate index or infer relationships from full text.

The benchmark report remains the evidence for parser versions, local commands,
and known limitations: [benchmark/BENCHMARK_REPORT.md](benchmark/BENCHMARK_REPORT.md).
