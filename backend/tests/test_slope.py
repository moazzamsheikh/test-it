"""M1.5 slope tests — hermetic (no live network calls).

get_or_compute_slope only reaches the remote LiDAR COG for a parcel NOT
already cached. Pre-seeding a ParcelSlopeResult row means the function must
serve entirely from the DB — this test proves that caching contract, not the
live-read path itself (verified by hand against the real dataset instead —
see DECISIONS.md/WALKTHROUGH.md — hitting a real 40GB remote file on every
test run would be slow and would repeatedly range-read a public government
file for no reason).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.models.slope import ParcelSlopeResult
from app.services.slope import LIDAR_MNT_URL, get_or_compute_slope


async def test_cached_parcel_returns_from_db_only(async_db_session: AsyncSession) -> None:
    """The real assertion: with a result already cached, get_or_compute_slope
    must not touch the network — if it tried, this test would hang or fail
    on DNS/timeout in a sandboxed run rather than complete in milliseconds."""
    parcel_id = (await async_db_session.execute(select(Parcel.id).limit(1))).scalar_one()
    async_db_session.add(
        ParcelSlopeResult(
            parcel_id=parcel_id,
            avg_slope_pct=4.9,
            max_slope_pct=34.0,
            min_elevation_m=322.2,
            max_elevation_m=324.1,
            sample_pixel_count=24905,
            source_url=LIDAR_MNT_URL,
        )
    )
    await async_db_session.flush()

    result = await get_or_compute_slope(async_db_session, parcel_id)

    assert result.avg_slope_pct == pytest.approx(4.9)
    assert result.sample_pixel_count == 24905


async def test_uncached_parcel_with_no_id_raises_not_a_cache_hit(
    async_db_session: AsyncSession,
) -> None:
    """A parcel id with no cached row and no matching Parcel row at all must
    fail loudly (scalar_one() raising), not silently return an empty result —
    guards against ever masking a real lookup bug as "no slope data"."""
    with pytest.raises(Exception):  # noqa: B017 - sqlalchemy.exc.NoResultFound, deliberately broad
        await get_or_compute_slope(async_db_session, uuid.uuid4())
