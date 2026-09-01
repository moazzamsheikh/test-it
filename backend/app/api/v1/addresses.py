"""M1.2 address search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.address import AddressSearchResult
from app.services.address_search import search_addresses

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.get("/search", response_model=list[AddressSearchResult])
async def search(
    q: str = Query(..., min_length=2, description="e.g. '1 Rue du Fort Thüngen'"),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[AddressSearchResult]:
    return await search_addresses(session, q, limit)
