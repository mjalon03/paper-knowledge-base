# Document parser benchmark report

Generated benchmark artifacts are intentionally local-only under `benchmark/output/`.
This report records the source versions and results observed on 2026-08-18. It is a
small decision benchmark, not a published accuracy study.

## Repository and environment audit

- Benchmark branch: `chore/document-parser-benchmark`, created from `main` and
  `origin/main` at `d8b422e` (`feat: add PDF reading order reconstruction (#5)`).
- The untracked title-detection experiment on `feat/title-detection` was preserved
  before switching as `stash@{0}: pre-parser-benchmark-safety`. It is not merged,
  modified, or deleted by this work.
- Existing merged modules: ingestion, raw PyMuPDF text extraction, layout extraction,
  and reading-order reconstruction. The experimental `structure/title.py` exists only
  in that stash.
- The three PDFs in `data/` are ignored by the `data/*` rule. The benchmark's raw
  outputs, external checkouts, models, caches, and synthetic scan are also ignored.

| Property | Observed value |
| --- | --- |
| OS | macOS 26.5, arm64 |
| CPU/GPU | Apple M4 Pro (12 CPU cores, 16 GPU cores), Metal supported |
| RAM / free disk | 24 GB unified memory / 107 GB free |
| Python / uv | 3.13.7 / 0.12.5 |
| Docker / CUDA | Docker unavailable; no NVIDIA CUDA GPU |
| Java / Homebrew | Java 21.0.6 / Homebrew 6.0.18 |
| PyTorch MPS check | Docling's Torch 2.13.0 reports built=`true`, available=`false`; all Docling runs used CPU |

The three real papers are born-digital: PyMuPDF extracted 8,527, 10,347, and 4,890
characters respectively from their first two pages. A three-page, 200-DPI image-only
version of the Gorzo paper was generated under `benchmark/fixtures/generated/`; its
selectable-text count is exactly zero.

## Candidate verification and feasibility gate

Version pins are in `config/tools.json`; each came from the current official GitHub
release API on 2026-08-18. Feature descriptions below are limited to the linked
official repository/documentation, not third-party comparisons.

| Tool | Verified release | License | Local class | Why |
| --- | --- | --- | --- | --- |
| [GROBID](https://github.com/grobidOrg/grobid) | 0.9.1 | Apache-2.0 | A | Native ARM macOS build is documented with Java 21; default CRF models are packaged. |
| [Marker](https://github.com/datalab-to/marker) | v2.0.0 | GPL code; model weights modified AI Pubs Open Rail-M | B | PyTorch/model download and roughly 4 GB VRAM per task are documented; no MPS was available in the installed Torch check. |
| [Chandra](https://github.com/datalab-to/chandra) | v0.2.0 | Apache-2.0 | B | Official local HuggingFace mode exists, but the recommended vLLM path is GPU-oriented and the 4B VLM is a substantial new model download. |
| [MinerU](https://github.com/opendatalab/MinerU) | mineru-3.4.5-released | MinerU Open Source License | B | Official docs allow Apple Silicon/CPU but specify 16 GB minimum, 32 GB recommended RAM and 20 GB+ disk for the hybrid path. |
| [olmOCR](https://github.com/allenai/olmocr) | v0.4.27 | Apache-2.0 | D | Official local inference requires a recent NVIDIA GPU with at least 12 GB VRAM and 30 GB free disk. |
| [AnyDoc](https://github.com/firecrawl/anydoc) | v0.1.9 | MIT | A (secondary) | Local Rust conversion is lightweight, but its own docs say scanned pages require OCR supplied by Firecrawl Parse rather than AnyDoc itself. |
| [Docling](https://github.com/docling-project/docling) | v2.120.2 | MIT | A | Officially supports arm64 macOS; ran locally on CPU. |
| [Surya](https://github.com/datalab-to/surya) | v0.22.1 | GPL code; model weights modified AI Pubs Open Rail-M | B (secondary) | OCR/layout/reading-order/table support is distinct, but it is a model-backed component and not needed before the core evidence. |

`A` means fully feasible, `B` feasible but heavy, `C` better through Docker, `D`
requires or strongly prefers NVIDIA GPU, and `E` not practical locally. None are
classified from a claimed benchmark score. Chandra and MinerU are deliberately deferred
despite being potentially runnable: this Mac meets only the documented minimum for
MinerU, and the first decision can be made from the executed semantic/layout pair.

### What the official tools expose

- GROBID is the academic-semantic specialist: TEI XML with header metadata, authors,
  affiliations, abstract, identifiers, sections, references, citation links, figures,
  tables, and optional coordinates; it supports batch/service deployment. It has no OCR
  fallback for an image-only PDF.
- Marker produces Markdown/structured output with layout, reading order, tables,
  equations, images/captions, and limited OCR; it is optimized for born-digital PDFs,
  not an academic-metadata authority.
- Chandra outputs Markdown, HTML, and JSON with layout, tables, math, images, and OCR;
  the official CLI has HuggingFace and vLLM modes.
- MinerU supports PDF/image/Office input, Markdown/JSON, layout, tables, equations,
  figures, OCR, CLI/API/WebUI, and a CPU `pipeline` backend. It does not claim GROBID's
  bibliographic/citation semantics.
- olmOCR is a GPU VLM that writes clean Markdown with OCR, equations, tables, headers /
  footers removal, and reading order. It is not installed or executed locally.
- AnyDoc is a local Markdown converter, not an OCR engine. Docling represents document
  structure with coordinates and exports Markdown, JSON/DoclingDocument, HTML, DocTags,
  and other formats; it supports multiple optional OCR engines. Surya is lower-level OCR,
  layout, reading-order, and table recognition and is also used by related Datalab tools.

## Executed evidence

All parser raw outputs, normalized JSON, timing JSON, command stderr/stdout, and generated
images remain in ignored `benchmark/output/`. “Exact” below means comparison with the
small local ground-truth manifest, not a claim of perfect extraction of every token.

### GROBID 0.9.1, local native CRF service

The official source at tag `0.9.1` was cloned to the ignored external directory and run
with Java 21. The service reported `{version: 0.9.1, revision: 0.9.1}`. The adapter stored
raw TEI and then normalized only explicit TEI elements.

| PDF | Runtime | Title / expected authors / DOI / abstract opening | Major sections | References | Citation links |
| --- | ---: | --- | --- | ---: | --- |
| Gorzo (17 pp.) | 11.779 s | exact / 2 of 2 / exact / found | 4 of 5 | 128 | 170 of 170 callouts target a bibliography id |
| Reising (20 pp.) | 2.465 s | exact / 4 of 4, plus 2 spurious reviewer/editor names / **not extracted** / found | 4 of 5 | 47 | 43 of 52 have a target |
| Wu (29 pp.) | 2.139 s | exact / 5 of 5 / exact / found | 2 of 5 | 22 | 16 of 16 callouts target a bibliography id |

The structured TEI also exposed coordinates for all three. Normalized object counts were:
Gorzo 1 table / 1 figure / 0 formulas, Reising 0 / 25 / 8, and Wu 5 / 13 / 0.
Those counts are detections, not manually adjudicated recall. The Reising result is the
important limitation: the first-page editorial/reviewer block was classified as authors,
and the article DOI was not emitted as the header identifier. This is why the result
supports GROBID as the academic parser, but not without per-paper validation and a DOI
fallback policy.

On the image-only synthetic PDF, GROBID returned HTTP 500 with `NO_BLOCKS: PDF parsing
resulted in empty content` in 1.036 s. That is a correct routing failure, not an OCR score.

### Docling 2.120.2, local CPU standard pipeline

Docling was installed only in `benchmark/.external/docling-venv`. The born-digital runs
used `--no-ocr`; the synthetic scan used automatic OCR. Native Docling JSON, Markdown,
referenced images, and timing output were retained locally. Its normalizer intentionally
does **not** invent title, author, DOI, affiliation, or abstract fields when the native
DoclingDocument does not label them as such.

| Input | Runtime | Native structural output | Qualitative observation |
| --- | ---: | --- | --- |
| Gorzo | 151.978 s | 13 section headers, 1 table, 2 pictures, coordinates | Markdown starts with the exact title and author line; table/figure detections are plausible. First run included embedded images, hence its unusually large Markdown. |
| Reising | 37.048 s | 67 section headers, 5 tables, 10 pictures, coordinates | Rich layout recovered, but heading/picture count needs human review before using as canonical structure. |
| Wu | 37.439 s | 81 section headers, 6 tables, 48 pictures, coordinates | Rich protocol structure is retained; 48 picture detections indicate over/fragmented detection is possible. |
| Image-only Gorzo pages 1–3 | 57.424 s | 6 headers, 0 tables, 0 pictures, coordinates, 13,668 text characters | OCR recovered the title, author line, and abstract opening in Markdown. This is a qualitative fallback check, not CER/WER. |

One deliberately forced `--ocr-engine rapidocr` run failed before inference because the
optional `onnxruntime` component was absent. Re-running with Docling's installed automatic
OCR backend succeeded. That failure and the CPU/MPS result are retained in the ignored
command evidence; neither is silently counted as an OCR result.

### Not executed locally

Marker, Chandra, MinerU, olmOCR, AnyDoc, and Surya have no local benchmark result. This
is intentional, not “no” performance. Marker/Chandra/MinerU are deferred heavy work;
olmOCR requires unavailable NVIDIA hardware; AnyDoc and Surya are secondary after the
core semantic/layout decision. No upstream score is substituted for a local result.

## Reproducible harness

Run these from the repository root. All generated files remain ignored.

```bash
# Verify the harness and create the OCR fixture.
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -m benchmark.scripts.create_synthetic_scan \
  data/2022_Gorzo_Photonics_Tools_Astrocyte_Calcium_Transients.pdf \
  benchmark/fixtures/generated/gorzo-first-3-pages-image-only.pdf --pages 3 --dpi 200

# Native GROBID from its official pinned source checkout (or point to a server).
git clone --depth 1 --branch 0.9.1 https://github.com/grobidOrg/grobid.git benchmark/.external/grobid
(cd benchmark/.external/grobid && ./gradlew run)
uv run python -m benchmark.scripts.run_grobid \
  data/2022_Gorzo_Photonics_Tools_Astrocyte_Calcium_Transients.pdf \
  benchmark/output/grobid/2022_Gorzo_Photonics_Tools_Astrocyte_Calcium_Transients \
  --endpoint http://127.0.0.1:8070 --version 0.9.1

# Collect per-document summaries and compare explicit normalized fields.
uv run python -m benchmark.scripts.collect_results benchmark/output/grobid benchmark/output/grobid/normalized-all
uv run python -m benchmark.scripts.evaluate_results \
  --manifest benchmark/config/ground_truth.json \
  --results-dir benchmark/output/grobid/normalized-all \
  --output benchmark/output/grobid/evaluation.json
```

`run_external_command.py` is the thin command recorder for future Marker, Chandra,
MinerU, olmOCR, AnyDoc, and Surya invocations. It preserves stdout/stderr, command,
return code, runtime, and native outputs even on failure. `normalize_grobid.py` and
`normalize_docling.py` allow a saved native run to be normalized again without rerunning
the parser. Use a fresh ignored environment for every external tool, record `--version`,
and add its pinned version/commit to `config/tools.json` before a server run.

For a later Ubuntu GPU host, keep the same input manifest and synthetic fixture. Start
with MinerU's documented CPU `pipeline` command if GPU access is unavailable; use its VLM
mode, Chandra vLLM, or olmOCR only on a verified NVIDIA host. olmOCR's official local
requirements are a recent NVIDIA GPU with at least 12 GB VRAM and 30 GB free disk. Record
GPU model, driver/CUDA, model revision, command, and peak memory alongside outputs.

## Recommendation and next step

The current evidence supports **Pattern D: GROBID + Docling, with a separate GPU OCR
candidate later**.

```text
inspect PDF (existing ingestion + lightweight PyMuPDF)
  ├─ usable embedded text
  │    ├─ GROBID TEI: canonical title/authors/affiliations/abstract/DOI,
  │    │  sections, references, citation links, coordinates
  │    └─ Docling JSON/Markdown: layout order, tables, formulas, figures, captions,
  │       page coordinates (use only after document-level QC)
  └─ insufficient text or GROBID NO_BLOCKS
       └─ Docling OCR now; benchmark Chandra or olmOCR on a NVIDIA server before
          selecting the long-term OCR owner
```

Ownership should be explicit: GROBID owns scholarly metadata and bibliography/citation
relationships; Docling currently owns layout-rich full text, tables, pictures, and the
working local OCR fallback; no tool has yet earned unconditional ownership of math or
figure/table recall. Preserve native TEI and DoclingDocument JSON; downstream data should
refer back to them rather than flattening incompatible concepts into one lossy schema.

Keep `ingestion/pdf.py` and SHA-256/file validation. Keep `pdf_text.py` and
`pdf_layout.py` as lightweight inspection/debug utilities. Freeze—not delete—
`reading_order.py` and the stashed `structure/title.py`; do not grow homemade academic
metadata or reading-order heuristics until a production parser's QC failures demonstrate a
specific gap. The next implementation should be a small routing/QC layer that records text
coverage, GROBID success/error, required-metadata completeness, and parser provenance per
paper, followed by a GPU-host comparison of Chandra/olmOCR (and MinerU if its layout is
needed) on this exact manifest.
