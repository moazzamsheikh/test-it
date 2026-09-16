"""M2.1 observability — reads the real `sources` table every ingestion
script already writes to (last_fetch_at/last_success_at/last_status/
documents_ingested), rather than a separate tracking mechanism."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import Source


async def list_source_statuses(session: AsyncSession) -> list[Source]:
    return list((await session.execute(select(Source).order_by(Source.name))).scalars().all())
