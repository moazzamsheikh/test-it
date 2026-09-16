"""M2.1 — the required "status table or dashboard showing, per source: last
successful fetch, documents ingested, failures, staleness"."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.source_status import SourceStatusInfo
from app.services.source_status import list_source_statuses

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/status", response_model=list[SourceStatusInfo])
async def get_source_statuses(
    session: AsyncSession = Depends(get_session),
) -> list[SourceStatusInfo]:
    sources = await list_source_statuses(session)
    return [
        SourceStatusInfo(
            id=s.id,
            name=s.name,
            source_url=s.source_url,
            publisher=s.publisher,
            access_method=s.access_method.value,
            last_fetch_at=s.last_fetch_at,
            last_success_at=s.last_success_at,
            last_status=s.last_status.value,
            last_error=s.last_error,
            failure_count=s.failure_count,
            documents_ingested=s.documents_ingested,
            updated_at=s.updated_at,
        )
        for s in sources
    ]
