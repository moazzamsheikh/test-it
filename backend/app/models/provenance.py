"""Provenance-first schema: sources, documents, chunks.

Design notes (see DECISIONS.md):
- Chunks carry DENORMALISED filter fields (commune_code, language, legal_status,
  document_date, document_type) so retrieval filters the search space *before*
  vector/lexical scoring and excludes repealed text with no join.
- Amendment chains are modelled as self-FKs supersedes_id / superseded_by_id
  plus the legal_status enum (covers the Legilux amendment-chain bonus).
- `documents` is the authoritative provenance record; chunk copies are stamped
  at ingest and re-stamped if a document's status changes.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import (
    AccessMethod,
    DocumentType,
    Language,
    LegalStatus,
    SourceStatus,
)

# Embedding dimension pinned to a 1024-d multilingual model (BGE-m3 class).
# Changing the model to a different dimension is an explicit migration.
EMBEDDING_DIM = 1024

# Shared enum type instances — reused across tables so each PG enum type is
# created exactly once by a single CREATE TYPE.
_legal_status = SAEnum(LegalStatus, name="legal_status")
_language = SAEnum(Language, name="language")
_document_type = SAEnum(DocumentType, name="document_type")


class Source(Base):
    """A feed/endpoint we crawl. Drives incremental fetch + the status dashboard."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    source_url: Mapped[str] = mapped_column(Text)
    access_method: Mapped[AccessMethod] = mapped_column(SAEnum(AccessMethod, name="access_method"))
    publisher: Mapped[str | None] = mapped_column(String(200), default=None)
    commune_code: Mapped[str | None] = mapped_column(String(10), default=None, index=True)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    # Incremental-fetch state (M2.1: ETag / Last-Modified / content hash)
    etag: Mapped[str | None] = mapped_column(String(255), default=None)
    last_modified: Mapped[str | None] = mapped_column(String(255), default=None)
    last_content_hash: Mapped[str | None] = mapped_column(String(64), default=None)

    # Observability (M2.1: last fetch, docs ingested, failures, staleness)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_status: Mapped[SourceStatus] = mapped_column(
        SAEnum(SourceStatus, name="source_status"), default=SourceStatus.never_run
    )
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    documents_ingested: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list[Document]] = relationship(back_populates="source")


class Document(Base):
    """One fetched artifact. Authoritative provenance record."""

    __tablename__ = "documents"
    __table_args__ = (
        # Idempotency key: same URL + same content is the same document.
        UniqueConstraint("source_url", "sha256", name="uq_documents_url_sha256"),
        Index("ix_documents_filters", "commune_code", "legal_status", "document_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), default=None
    )

    # Provenance (M2.2, non-negotiable)
    eli: Mapped[str | None] = mapped_column(String(500), unique=True, default=None)
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    publisher: Mapped[str | None] = mapped_column(String(200), default=None)
    document_date: Mapped[date | None] = mapped_column(default=None)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sha256: Mapped[str] = mapped_column(String(64))
    language: Mapped[Language] = mapped_column(_language, default=Language.unknown)
    commune_code: Mapped[str | None] = mapped_column(String(10), default=None)
    legal_status: Mapped[LegalStatus] = mapped_column(_legal_status, default=LegalStatus.unknown)
    document_type: Mapped[DocumentType] = mapped_column(_document_type)

    # Amendment chain
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), default=None
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), default=None
    )

    storage_path: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[Source | None] = relationship(back_populates="documents")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """A retrievable passage. Carries denormalised filter fields + embedding + tsv."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_filters", "commune_code", "legal_status", "document_type"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    article_ref: Mapped[str | None] = mapped_column(String(100), default=None)
    heading: Mapped[str | None] = mapped_column(Text, default=None)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer, default=None)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), default=None)

    # Lexical search vector — 'simple' config (no stemming) preserves article
    # numbers, defined terms and rare tokens, which is exactly what legal
    # hybrid search needs. Revisited per-language in M3 if warranted.
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True),
    )

    # Denormalised filter fields (Option B)
    commune_code: Mapped[str | None] = mapped_column(String(10), default=None)
    language: Mapped[Language] = mapped_column(_language, default=Language.unknown)
    legal_status: Mapped[LegalStatus] = mapped_column(_legal_status, default=LegalStatus.unknown)
    document_date: Mapped[date | None] = mapped_column(default=None)
    document_type: Mapped[DocumentType] = mapped_column(_document_type)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")
