"""Guards the axis-swap self-check in ingest_pag_zones.py (see DECISIONS.md):
ACT's own per-commune PAG GML exports disagree on axis order — verified
live that Wiltz's needed swapping (0% overlap with real parcels as parsed,
correct overlap once swapped) while Luxembourg City's didn't. Rather than
trust either orientation blindly, ingestion checks against that commune's
own already-ingested real parcels and uses whichever orientation actually
overlaps — this test proves that logic against real Wiltz parcel geometry,
not synthetic data, since the whole point is cross-checking against reality.
"""

from __future__ import annotations

from geoalchemy2.shape import to_shape
from shapely.geometry import MultiPolygon
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from ingestion.ingest_pag_zones import _resolve_axis_swap, _swap_xy


async def _real_wiltz_parcel_multipolygon(session: AsyncSession) -> MultiPolygon:
    parcel = (
        await session.execute(select(Parcel).where(Parcel.admin_commune_code == "0807").limit(1))
    ).scalar_one()
    geom = to_shape(parcel.geom)
    return geom if isinstance(geom, MultiPolygon) else MultiPolygon([geom])


async def test_correctly_oriented_geometry_needs_no_swap(async_db_session: AsyncSession) -> None:
    """A real Wiltz parcel's own geometry, used as the 'sample', trivially
    overlaps itself — proving the as-parsed branch is taken when the
    orientation is already correct."""
    sample = await _real_wiltz_parcel_multipolygon(async_db_session)

    needs_swap = await async_db_session.run_sync(
        lambda sync_session: _resolve_axis_swap(sync_session, "0807", [sample])
    )
    assert needs_swap is False


async def test_swapped_geometry_is_detected_and_flagged(async_db_session: AsyncSession) -> None:
    """The same real parcel geometry, deliberately swapped, must be detected
    as needing a swap — not silently accepted as 'no overlap, must be a
    real gap'."""
    swapped_sample = _swap_xy(await _real_wiltz_parcel_multipolygon(async_db_session))

    needs_swap = await async_db_session.run_sync(
        lambda sync_session: _resolve_axis_swap(sync_session, "0807", [swapped_sample])
    )
    assert needs_swap is True
