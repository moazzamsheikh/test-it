"""M1.5 buildable envelope tests — real ingested data, real PostGIS buffer."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.services.geometry_analysis import compute_buildable_envelope


async def _parcel_id(session: AsyncSession, cadastral_id: str) -> uuid.UUID:
    return (
        await session.execute(select(Parcel.id).where(Parcel.cadastral_id == cadastral_id))
    ).scalar_one()


async def test_moderate_setback_returns_a_real_smaller_polygon(
    async_db_session: AsyncSession,
) -> None:
    parcel_id = await _parcel_id(async_db_session, "054A00396005426")
    area_m2, geojson = await compute_buildable_envelope(async_db_session, parcel_id, 5.0)
    assert geojson is not None
    assert 0 < area_m2 < 6226.7  # strictly smaller than the parcel's own area_geom_m2


async def test_zero_setback_returns_the_full_parcel(async_db_session: AsyncSession) -> None:
    parcel_id = await _parcel_id(async_db_session, "054A00396005426")
    area_m2, geojson = await compute_buildable_envelope(async_db_session, parcel_id, 0.0)
    assert geojson is not None
    assert area_m2 == pytest.approx(6226.69455704583, abs=0.01)


async def test_large_setback_fully_erodes_the_parcel(async_db_session: AsyncSession) -> None:
    parcel_id = await _parcel_id(async_db_session, "054A00396005426")
    area_m2, geojson = await compute_buildable_envelope(async_db_session, parcel_id, 100.0)
    assert geojson is None
    assert area_m2 == 0.0
