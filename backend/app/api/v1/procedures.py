"""M5 procedure endpoint — see DECISIONS.md: a structured, citation-backed
display of one real ingested government procedure, not a chatbot (M3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.procedure import ProcedureDetail
from app.services.procedures import get_building_permit_procedure

router = APIRouter(prefix="/procedures", tags=["procedures"])


@router.get("/building-permit", response_model=ProcedureDetail)
async def building_permit(session: AsyncSession = Depends(get_session)) -> ProcedureDetail:
    procedure = await get_building_permit_procedure(session)
    if procedure is None:
        raise HTTPException(
            status_code=404,
            detail="not ingested yet — run `make ingest-procedures`",
        )
    return procedure
