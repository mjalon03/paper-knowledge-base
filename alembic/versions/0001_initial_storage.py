"""Create the initial paper storage schema."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial_storage"
down_revision = None
branch_labels = None
depends_on = None


def _uuid() -> sa.Uuid:
    return sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("canonical_title", sa.String(length=2000), nullable=True),
        sa.Column("normalized_title", sa.String(length=2000), nullable=True),
        sa.Column("doi", sa.String(length=512), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("venue_name", sa.String(length=1000), nullable=True),
        sa.Column("publisher", sa.String(length=1000), nullable=True),
        sa.Column("volume", sa.String(length=100), nullable=True),
        sa.Column("issue", sa.String(length=100), nullable=True),
        sa.Column("pages", sa.String(length=200), nullable=True),
        sa.Column("work_type", sa.String(length=100), nullable=True),
        sa.Column("canonical_confidence", sa.String(length=32), nullable=True),
        sa.Column("metadata_provenance_json", sa.JSON(), nullable=False),
        sa.Column("metadata_evidence_json", sa.JSON(), nullable=False),
        sa.Column("metadata_conflicts_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doi"),
    )
    op.create_index("ix_papers_normalized_title", "papers", ["normalized_title"])
    op.create_index("ix_papers_publication_year", "papers", ["publication_year"])
    op.create_index("ix_papers_doi", "papers", ["doi"])

    op.create_table(
        "documents",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=1000), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_identifier", sa.String(length=1000), nullable=True),
        sa.Column("source_uri", sa.String(length=2000), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("has_embedded_text", sa.Boolean(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", sa.String(length=32), nullable=True),
        sa.Column("processing_route", sa.String(length=32), nullable=True),
        sa.Column("processing_metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    op.create_table(
        "authors",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("given_name", sa.String(length=300), nullable=True),
        sa.Column("family_name", sa.String(length=300), nullable=True),
        sa.Column("normalized_name", sa.String(length=500), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_authors_normalized_name", "authors", ["normalized_name"])

    op.create_table(
        "paper_documents",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("paper_id", _uuid(), nullable=False),
        sa.Column("document_id", _uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "document_id", name="uq_paper_documents_pair"),
        sa.UniqueConstraint("document_id", name="uq_paper_documents_one_paper"),
    )
    op.create_index("ix_paper_documents_paper_id", "paper_documents", ["paper_id"])

    op.create_table(
        "paper_relations",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("source_paper_id", _uuid(), nullable=False),
        sa.Column("target_paper_id", _uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "source_paper_id <> target_paper_id", name="ck_paper_relations_not_self"
        ),
        sa.ForeignKeyConstraint(
            ["source_paper_id"], ["papers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_paper_id"], ["papers.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_paper_id",
            "target_paper_id",
            "relation_type",
            name="uq_paper_relations_edge",
        ),
    )
    op.create_index("ix_paper_relations_source", "paper_relations", ["source_paper_id"])
    op.create_index("ix_paper_relations_target", "paper_relations", ["target_paper_id"])

    op.create_table(
        "paper_authors",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("paper_id", _uuid(), nullable=False),
        sa.Column("author_id", _uuid(), nullable=False),
        sa.Column("author_position", sa.Integer(), nullable=False),
        sa.Column("is_corresponding", sa.Boolean(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["author_id"], ["authors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "author_id", name="uq_paper_authors_pair"),
        sa.UniqueConstraint(
            "paper_id", "author_position", name="uq_paper_authors_position"
        ),
    )
    op.create_index("ix_paper_authors_paper_id", "paper_authors", ["paper_id"])


def downgrade() -> None:
    op.drop_index("ix_paper_authors_paper_id", table_name="paper_authors")
    op.drop_table("paper_authors")
    op.drop_index("ix_paper_relations_target", table_name="paper_relations")
    op.drop_index("ix_paper_relations_source", table_name="paper_relations")
    op.drop_table("paper_relations")
    op.drop_index("ix_paper_documents_paper_id", table_name="paper_documents")
    op.drop_table("paper_documents")
    op.drop_index("ix_authors_normalized_name", table_name="authors")
    op.drop_table("authors")
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_papers_doi", table_name="papers")
    op.drop_index("ix_papers_publication_year", table_name="papers")
    op.drop_index("ix_papers_normalized_title", table_name="papers")
    op.drop_table("papers")
