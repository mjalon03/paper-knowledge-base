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
canonical truth: Crossref/OpenAlex resolution and author reconciliation remain
future work. In particular, the benchmark still shows the known Reising author
anomaly and missing DOI; this pipeline preserves rather than repairs them.

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

The benchmark report remains the evidence for parser versions, local commands,
and known limitations: [benchmark/BENCHMARK_REPORT.md](benchmark/BENCHMARK_REPORT.md).
