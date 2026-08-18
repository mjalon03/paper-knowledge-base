# Document parser benchmark

See [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md) for the verified tool matrix, executed
results, and recommended routing architecture.

This directory is isolated from the production package:

- `config/` contains the small ground-truth manifest and version pins.
- `adapters/` preserves each parser's native output and creates a loss-aware summary.
- `scripts/` creates the image-only fixture, runs adapters, normalizes saved output, and
  evaluates explicit ground-truth fields.
- `fixtures/`, `reports/`, and `output/` hold local benchmark material; generated files
  are ignored.

Run the checks and fixture generation with:

```bash
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -m benchmark.scripts.create_synthetic_scan \
  data/2022_Gorzo_Photonics_Tools_Astrocyte_Calcium_Transients.pdf \
  benchmark/fixtures/generated/gorzo-first-3-pages-image-only.pdf
```
