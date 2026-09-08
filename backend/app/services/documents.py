"""Shared helper for resolving a `documents.id` into an API-facing
`DocumentReference` — used by every service that cites a real ingested
document (PAG zoning, and now the M1.4 static overlay documents)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import Chunk, Document
from app.schemas.pag import DocumentReference


async def get_document_reference(
    session: AsyncSession, document_id: uuid.UUID | None
) -> DocumentReference | None:
    """Single-chunk documents (a PAG zone's own written text, M5's
    procedure) show that chunk's article_ref/text directly, same as before.
    Multi-article documents (a full règlement grand-ducal, ingested as one
    chunk per real `Art. N` — see ingestion/legilux_extraction.py) show only
    the document-level citation: dumping 10+ articles inline in a
    constraint card isn't useful, and the real full text stays reachable
    via `source_url` (and will be searchable once M3's retrieval exists)."""
    if document_id is None:
        return None
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        return None
    chunks = (
        (
            await session.execute(
                select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal)
            )
        )
        .scalars()
        .all()
    )
    if len(chunks) == 1:
        return DocumentReference(
            title=document.title or "",
            source_url=document.source_url,
            article_ref=chunks[0].article_ref,
            text=chunks[0].text,
        )
    return DocumentReference(
        title=document.title or "", source_url=document.source_url, article_ref=None, text=None
    )
