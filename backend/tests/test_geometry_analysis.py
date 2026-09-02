"""M1.5 frontage/neighbour tests — real ingested Wiltz + Luxembourg City data,
not fixtures (see conftest.py: real DB, transaction rolled back at teardown).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.services.geometry_analysis import compute_frontage_m, compute_neighbours


async def _parcel_id(session: AsyncSession, cadastral_id: str):
    return (
        await session.execute(select(Parcel.id).where(Parcel.cadastral_id == cadastral_id))
    ).scalar_one()


async def test_frontage_is_positive_for_a_parcel_touching_a_road(
    async_db_session: AsyncSession,
) -> None:
    """054A00396005426 was verified by hand to directly touch a road-nature
    parcel (ST_Intersects against parcels.nature_code in ROAD_NATURE_CODES) —
    frontage must be a real positive length, not zero."""
    parcel_id = await _parcel_id(async_db_session, "054A00396005426")
    frontage_m = await compute_frontage_m(async_db_session, parcel_id)
    assert frontage_m == pytest.approx(23.999521348031777, abs=0.01)


async def test_frontage_is_zero_for_a_landlocked_parcel(async_db_session: AsyncSession) -> None:
    """054A00242005292 is surrounded entirely by other private parcels (all 20
    of its nearest neighbours are at distance 0.0, i.e. touching) — no
    road-nature parcel touches it directly, so 0.0 is the honest result."""
    parcel_id = await _parcel_id(async_db_session, "054A00242005292")
    frontage_m = await compute_frontage_m(async_db_session, parcel_id)
    assert frontage_m == 0.0


async def test_neighbours_are_sorted_nearest_first_and_capped(
    async_db_session: AsyncSession,
) -> None:
    parcel_id = await _parcel_id(async_db_session, "054A00242005292")
    neighbours = await compute_neighbours(async_db_session, parcel_id)
    assert len(neighbours) == 20  # the configured cap, all touching (distance 0) here
    distances = [n.distance_m for n in neighbours]
    assert distances == sorted(distances)
    assert all(d >= 0.0 for d in distances)
    cadastral_ids = {n.cadastral_id for n in neighbours}
    assert "054A00242005292" not in cadastral_ids  # never lists itself
