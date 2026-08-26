"""initial provenance schema

Revision ID: aebf224488fd
Revises:
Create Date: 2026-08-26 11:28:40.042130
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "aebf224488fd"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Native enum types created once up front. `create_type=False` stops create_table
# from re-emitting CREATE TYPE for the types shared by documents + chunks.
access_method = postgresql.ENUM(
    "api",
    "bulk",
    "scrape",
    "wfs",
    "wms",
    "wmts",
    "sparql",
    name="access_method",
    create_type=False,
)
source_status = postgresql.ENUM(
    "never_run",
    "ok",
    "failed",
    "stale",
    name="source_status",
    create_type=False,
)
language = postgresql.ENUM(
    "fr",
    "de",
    "lb",
    "en",
    "unknown",
    name="language",
    create_type=False,
)
legal_status = postgresql.ENUM(
    "in_force",
    "repealed",
    "draft",
    "superseded",
    "unknown",
    name="legal_status",
    create_type=False,
)
document_type = postgresql.ENUM(
    "loi",
    "reglement_grand_ducal",
    "pag_written",
    "pag_graphic",
    "pap_qe",
    "pap_nq",
    "building_bylaw",
    "other_bylaw",
    "sectoral_plan",
    "geospatial_layer",
    "procedure_guide",
    "form",
    "other",
    name="document_type",
    create_type=False,
)

_ALL_ENUMS = (access_method, source_status, language, legal_status, document_type)


def upgrade() -> None:
    # Re-assert extensions so a fresh `alembic upgrade` works on any empty DB,
    # not only the compose box whose init script already created them.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    bind = op.get_bind()
    for enum_type in _ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("access_method", access_method, nullable=False),
        sa.Column("publisher", sa.String(length=200), nullable=True),
        sa.Column("commune_code", sa.String(length=10), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("last_modified", sa.String(length=255), nullable=True),
        sa.Column("last_content_hash", sa.String(length=64), nullable=True),
        sa.Column("last_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", source_status, nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("documents_ingested", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_sources_commune_code"), "sources", ["commune_code"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("eli", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("publisher", sa.String(length=200), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("language", language, nullable=False),
        sa.Column("commune_code", sa.String(length=10), nullable=True),
        sa.Column("legal_status", legal_status, nullable=False),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eli"),
        sa.UniqueConstraint("source_url", "sha256", name="uq_documents_url_sha256"),
    )
    op.create_index(
        "ix_documents_filters",
        "documents",
        ["commune_code", "legal_status", "document_type"],
        unique=False,
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("article_ref", sa.String(length=100), nullable=True),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True),
            nullable=True,
        ),
        sa.Column("commune_code", sa.String(length=10), nullable=True),
        sa.Column("language", language, nullable=False),
        sa.Column("legal_status", legal_status, nullable=False),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False)
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_chunks_filters",
        "chunks",
        ["commune_code", "legal_status", "document_type"],
        unique=False,
    )
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], unique=False, postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_chunks_tsv", table_name="chunks", postgresql_using="gin")
    op.drop_index("ix_chunks_filters", table_name="chunks")
    op.drop_index(
        "ix_chunks_embedding_hnsw",
        table_name="chunks",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_documents_filters", table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_sources_commune_code"), table_name="sources")
    op.drop_table("sources")

    bind = op.get_bind()
    for enum_type in reversed(_ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
    # Extensions are intentionally NOT dropped: they are shared and may be used
    # by other schemas (e.g. the M1 spatial tables added in a later migration).
