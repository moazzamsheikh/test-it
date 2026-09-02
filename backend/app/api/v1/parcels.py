"""M1.3 parcel identification and detail endpoints.

Route order matters here: /identify and /by-reference must be registered
before /{cadastral_id}, or Starlette's path routing would match them as
cadastral_id values instead of the fixed routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.parcel import (
    BuildableEnvelope,
    ParcelDetail,
    ParcelIdentifyResponse,
    ParcelSummary,
)
from app.schemas.slope import SlopeResult
from app.services.geometry_analysis import compute_buildable_envelope
from app.services.parcels import (
    find_by_reference,
    get_parcel_detail,
    get_parcel_id,
    identify_by_point,
)
from app.services.slope import get_or_compute_slope

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


@router.get("/{cadastral_id}/slope", response_model=SlopeResult)
async def slope(
    cadastral_id: str,
    session: AsyncSession = Depends(get_session),
) -> SlopeResult:
    """Separate from the main detail endpoint on purpose: unlike frontage/
    neighbours (cheap PostGIS queries), an uncached slope computation does a
    multi-second remote LiDAR read — this stays a distinct, lazily-fetched
    call so it never blocks the rest of the parcel detail panel from loading
    (see DECISIONS.md)."""
    parcel_id = await get_parcel_id(session, cadastral_id)
    if parcel_id is None:
        raise HTTPException(status_code=404, detail="parcel not found")
    result = await get_or_compute_slope(session, parcel_id)
    return SlopeResult.model_validate(result, from_attributes=True)


@router.get("/{cadastral_id}/buildable-envelope", response_model=BuildableEnvelope)
async def buildable_envelope(
    cadastral_id: str,
    setback_m: float = Query(
        ...,
        ge=0,
        description=(
            "Manual inward setback in metres — PAG/PAP setback values aren't "
            "reliably extractable yet (legislation ingestion is M2, not started), "
            "so this is a manual input rather than a fabricated default (see DECISIONS.md)."
        ),
    ),
    session: AsyncSession = Depends(get_session),
) -> BuildableEnvelope:
    parcel_id = await get_parcel_id(session, cadastral_id)
    if parcel_id is None:
        raise HTTPException(status_code=404, detail="parcel not found")
    area_m2, geojson = await compute_buildable_envelope(session, parcel_id, setback_m)
    return BuildableEnvelope(
        setback_m=setback_m,
        envelope_area_m2=area_m2,
        is_empty=geojson is None,
        geometry_wgs84_geojson=geojson,
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
