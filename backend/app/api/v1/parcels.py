"""M1.3 parcel identification and detail endpoints.

Route order matters here: /identify and /by-reference must be registered
before /{cadastral_id}, or Starlette's path routing would match them as
cadastral_id values instead of the fixed routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.parcel import ParcelDetail, ParcelIdentifyResponse, ParcelSummary
from app.services.parcels import find_by_reference, get_parcel_detail, identify_by_point

router = APIRouter(prefix="/parcels", tags=["parcels"])


@router.get("/identify", response_model=ParcelIdentifyResponse)
async def identify(
    lon: float = Query(..., description="Longitude, WGS84 (EPSG:4326)"),
    lat: float = Query(..., description="Latitude, WGS84 (EPSG:4326)"),
    session: AsyncSession = Depends(get_session),
) -> ParcelIdentifyResponse:
    parcels = await identify_by_point(session, lon, lat)
    return ParcelIdentifyResponse(parcels=parcels)


@router.get("/by-reference", response_model=list[ParcelSummary])
async def by_reference(
    cadastral_commune_code: str = Query(..., min_length=1, max_length=3),
    section_code: str = Query(..., min_length=1, max_length=3),
    numero_principal: int = Query(..., ge=0),
    numero_secondaire: int | None = Query(None, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[ParcelSummary]:
    return await find_by_reference(
        session, cadastral_commune_code, section_code, numero_principal, numero_secondaire
    )


@router.get("/{cadastral_id}", response_model=ParcelDetail)
async def detail(
    cadastral_id: str,
    session: AsyncSession = Depends(get_session),
) -> ParcelDetail:
    parcel = await get_parcel_detail(session, cadastral_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="parcel not found")
    return parcel
