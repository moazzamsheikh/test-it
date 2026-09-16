"""M2.4 bonus — real amendment-chain resolution: given a law and a date,
which version was actually in force. See `app/services/legislation_versions.py`
and `ingestion/ingest_legislation_versions.py` for the real SPARQL data
behind this."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.legislation_version import LegislationVersionInfo
from app.services.legislation_versions import get_version_in_force, list_versions

router = APIRouter(prefix="/legislation", tags=["legislation"])


def _to_info(v: object) -> LegislationVersionInfo:
    return LegislationVersionInfo.model_validate(v, from_attributes=True)


@router.get("/version-at", response_model=LegislationVersionInfo)
async def get_version_at(
    work_eli: str = Query(..., description="The law's stable Legilux work ELI"),
    on_date: date = Query(..., description="Resolve the version in force on this date"),
    session: AsyncSession = Depends(get_session),
) -> LegislationVersionInfo:
    version = await get_version_in_force(session, work_eli, on_date)
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=f"no ingested version of {work_eli!r} was in force on or before {on_date}",
        )
    return _to_info(version)


@router.get("/versions", response_model=list[LegislationVersionInfo])
async def get_versions(
    work_eli: str = Query(..., description="The law's stable Legilux work ELI"),
    session: AsyncSession = Depends(get_session),
) -> list[LegislationVersionInfo]:
    return [_to_info(v) for v in await list_versions(session, work_eli)]
