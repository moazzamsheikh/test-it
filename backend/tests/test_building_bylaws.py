"""M2.3/M2.4 building bylaws — against real ingested PDFs, not fixtures.
See DECISIONS.md for the two real PDF-layout failure modes this surfaced."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import Chunk, Document
from ingestion.ingest_building_bylaws import BUILDING_BYLAWS


async def test_all_configured_bylaws_are_ingested_with_real_text(
    async_db_session: AsyncSession,
) -> None:
    for entry in BUILDING_BYLAWS:
        document = (
            await async_db_session.execute(select(Document).where(Document.source_url == entry.url))
        ).scalar_one_or_none()
        assert document is not None, f"{entry.commune_name} bylaw should be ingested"
        assert document.commune_code == entry.commune_code

        chunks = (
            (await async_db_session.execute(select(Chunk).where(Chunk.document_id == document.id)))
            .scalars()
            .all()
        )
        assert len(chunks) > 0, f"{entry.commune_name} bylaw should have real chunks"
        assert all(len(c.text) > 0 for c in chunks)


async def test_esch_splits_into_real_distinct_articles(async_db_session: AsyncSession) -> None:
    """Esch-sur-Alzette's real bylaw PDF splits cleanly per-article
    (verified live: 93 fragments, 92 distinct refs) — confirms the
    extractor's per-article path works for a well-formed PDF, not just the
    whole-document fallback."""
    document = (
        await async_db_session.execute(select(Document).where(Document.commune_code == "0204"))
    ).scalar_one()
    chunks = (
        (await async_db_session.execute(select(Chunk).where(Chunk.document_id == document.id)))
        .scalars()
        .all()
    )
    assert len(chunks) > 50
    refs = [c.article_ref for c in chunks if c.article_ref]
    assert len(set(refs)) > 50
