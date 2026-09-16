"""M2.3/M2.4 national legislation corpus (brief §3.3) — against the real
ingested rows (`make ingest-national-legislation`), not fixtures.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import Chunk, Document
from ingestion.ingest_national_legislation import NATIONAL_LAWS


async def test_all_configured_laws_are_ingested_with_real_articles(
    async_db_session: AsyncSession,
) -> None:
    for entry in NATIONAL_LAWS:
        document = (
            await async_db_session.execute(select(Document).where(Document.source_url == entry.url))
        ).scalar_one_or_none()
        assert document is not None, f"{entry.key} should be ingested"
        assert document.title

        chunks = (
            (await async_db_session.execute(select(Chunk).where(Chunk.document_id == document.id)))
            .scalars()
            .all()
        )
        assert len(chunks) > 0, f"{entry.key} should have real article chunks"
        assert all(c.legal_status == entry.legal_status for c in chunks)


async def test_acdu_2004_is_the_real_consolidated_text(async_db_session: AsyncSession) -> None:
    """The core communal-planning law — the assessment brief's own words —
    must resolve to a real ingested consolidated text with a plausible
    article count, not a stub."""
    document = (
        await async_db_session.execute(
            select(Document).where(Document.title.contains("aménagement communal"))
        )
    ).scalar_one_or_none()
    assert document is not None
    assert document.title.startswith("Version consolidée")

    chunks = (
        (await async_db_session.execute(select(Chunk).where(Chunk.document_id == document.id)))
        .scalars()
        .all()
    )
    assert len(chunks) > 50
