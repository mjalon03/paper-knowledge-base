# Persistent paper storage

Storage uses SQLAlchemy 2.0.52 with Alembic 1.19.1 and Psycopg 3.3.4. PostgreSQL
is the production target; SQLite is used for fast unit tests and migration
smoke tests. The default `DATABASE_URL` is an in-memory SQLite URL, so local
commands never connect to a production database unexpectedly.

The ORM is isolated under `paper_knowledge_base.storage`. Processing,
canonical metadata, and identity modules continue to expose their own domain
models; storage maps those values at the service boundary.

## Entities

```text
Paper
  canonical scholarly work and frequently queried metadata

Document
  one concrete PDF/artifact, identified uniquely by SHA-256

PaperDocument
  association from one Paper to one Document, including role/primary status

Author + PaperAuthor
  structured author rows with preserved order and field provenance

PaperRelation
  directed relationship between two Papers
```

A Document is constrained to one Paper through a unique `document_id` on
`PaperDocument`. This is the conservative current policy: one concrete file
belongs to one scholarly work. A Paper can have many Documents, such as a
publisher copy, repository copy, manuscript, and OCR-derived copy.

Relation direction is explicit: the source is the related/derived work and the
target is the work it refers to. Therefore a preprint relation is
`preprint VERSION_OF journal`, and a correction, retraction, or supplement is
`related_work CORRECTION_OF|RETRACTION_OF|SUPPLEMENT_OF original`.
`SAME_PAPER` is never stored as a PaperRelation; it reuses the target Paper and
adds another PaperDocument association.

## Persistence behavior

- `EXACT_FILE_DUPLICATE`: the unique SHA-256 reuses the existing Document and
  association.
- `SAME_PAPER`: reuse the supplied or DOI-resolved Paper and attach a new
  Document.
- `RELATED_VERSION`, correction, retraction, or supplement: create a separate
  Paper and a directed PaperRelation. The caller supplies `related_paper_id`.
- `DISTINCT` or `AMBIGUOUS`: create a separate Paper. Ambiguous evidence is
  retained rather than silently merged.

The storage service consumes an `IdentityDecision`; it does not perform title,
author, DOI, or fuzzy matching. Canonical fields are stored in columns, while
resolution evidence, conflicts, and field provenance are stored as compact JSON
without raw GROBID TEI, Docling JSON, or full API payloads. Parser status/route
and a compact processing summary are kept on Document so successful processing
can be recognized later.

Authors are not globally deduplicated by normalized name. Identical normalized
names can represent different people, so the current service creates a
structured Author row for each persisted paper author and preserves position in
PaperAuthor. ORCID/person resolution is future work.

UUIDs are internal primary keys; DOI and SHA-256 are business identifiers with
database uniqueness constraints. DOI is normalized before persistence. UTC-aware
timestamps are used in Python and normalized on SQLite reads because SQLite
does not retain timezone offsets.

Deletion is deliberately restrictive. Foreign keys use `RESTRICT`, and the
schema does not use broad `delete-orphan` cascades. A Paper or Document with
associations cannot be deleted accidentally; a future explicit archival or
administrative deletion workflow can define safe ordering.

## Migrations and tests

Production schema changes use Alembic, not `Base.metadata.create_all()`.

```bash
DATABASE_URL=postgresql+psycopg://... uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://... uv run alembic downgrade base
DATABASE_URL=postgresql+psycopg://... uv run alembic upgrade head
uv run pytest
```

The default suite uses isolated SQLite databases and requires no network or
PostgreSQL. Optional PostgreSQL checks require an explicitly dedicated database
and are marked `storage_integration`:

```bash
PKB_RUN_STORAGE_INTEGRATION=1 \
DATABASE_URL=postgresql+psycopg://... \
uv run pytest -m storage_integration
```
