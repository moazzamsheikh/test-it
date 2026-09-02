"""M1.4 overlay tests — hermetic (no live network calls).

get_or_compute_overlays only queries the external WMS for layers NOT already
cached for a parcel. Pre-seeding a ParcelOverlayResult row for every
configured layer means the function must serve entirely from the DB — these
tests prove that caching contract, not the live-query path itself (verified
by hand against real data instead — see DECISIONS.md/WALKTHROUGH.md — since
exercising the real external WMS in every test run would be slow and would
repeatedly hit a free public server for no reason).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.models.overlays import ParcelOverlayResult
from app.overlay_layers import OVERLAY_LAYERS
from app.services.overlays import get_or_compute_overlays


async def _seed_all_layers_cached(session: AsyncSession, parcel_id: uuid.UUID) -> None:
    for i, layer in enumerate(OVERLAY_LAYERS):
        session.add(
            ParcelOverlayResult(
                id=uuid.uuid4(),
                parcel_id=parcel_id,
                layer_code=layer.code,
                intersects=(i == 0),  # exactly one real hit, for a clean assertion
                overlap_m2=42.0 if i == 0 else None,
                detail={"fake": "seed"} if i == 0 else None,
                source_url=layer.source_url,
            )
        )
    await session.flush()


async def test_fully_cached_parcel_returns_from_db_only(async_db_session: AsyncSession) -> None:
    """The real assertion: with every layer already cached, get_or_compute_overlays
    must not need to reach the network at all — if it tried, this test would hang
    or fail on DNS/timeout in a sandboxed run rather than complete in milliseconds."""
    parcel_id = (await async_db_session.execute(select(Parcel.id).limit(1))).scalar_one()
    await _seed_all_layers_cached(async_db_session, parcel_id)

    results = await get_or_compute_overlays(async_db_session, parcel_id)

    assert {r.layer_code for r in results} == {layer.code for layer in OVERLAY_LAYERS}
    hit = next(r for r in results if r.layer_code == OVERLAY_LAYERS[0].code)
    assert hit.intersects is True
    assert hit.overlap_m2 == pytest.approx(42.0)
    miss = next(r for r in results if r.layer_code == OVERLAY_LAYERS[1].code)
    assert miss.intersects is False
    assert miss.overlap_m2 is None
