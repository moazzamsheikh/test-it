"""M2 PAG zoning tests — against the real ingested data (see
`make ingest-pag-zones`), not fixtures. Mirrors the M1.5/M1.4 approach:
real parcels, real assertions, real (sometimes surprising) results."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.services.pag_zoning import get_pag_zoning


async def _parcel_id(session: AsyncSession, cadastral_id: str):
    return (
        await session.execute(select(Parcel.id).where(Parcel.cadastral_id == cadastral_id))
    ).scalar_one()


async def test_real_parcel_resolves_to_its_real_pag_zone(async_db_session: AsyncSession) -> None:
    """075F00184002448 ("8 Rue Beck") was independently verified (Nominatim,
    live WMS imagery, and the real Art.19 legal text) to genuinely fall
    within a "FOR" (zone forestière) polygon — a real, surprising result
    from real data, reported as-is rather than second-guessed. See
    DECISIONS.md for the full investigation."""
    parcel_id = await _parcel_id(async_db_session, "075F00184002448")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    assert len(zoning.pag_zones) == 1
    match = zoning.pag_zones[0]
    assert match.category == "FOR"
    assert match.overlap_m2 > 0
    assert match.document is not None
    assert match.document.article_ref == "Art. 19"
    assert "forestière" in match.document.text.lower()


async def test_parcel_with_no_pag_coverage_returns_an_empty_list(
    async_db_session: AsyncSession,
) -> None:
    """054A00396005426 falls in a real, confirmed gap in the downloadable
    PAG bulk export (verified via the live WMS image showing real zoning
    there that this dataset doesn't include — see DECISIONS.md) — an empty
    list is the honest result, not an error or a fabricated zone."""
    parcel_id = await _parcel_id(async_db_session, "054A00396005426")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    assert zoning.pag_zones == []
    assert zoning.pap_qe_zones == []


async def test_real_parcel_resolves_real_nq_pap_coefficients(
    async_db_session: AsyncSession,
) -> None:
    """101A00986003628 genuinely intersects several real NQ_PAP ("Nouveau
    Quartier") zones — verified live against ACT's own GML data, which
    carries COS/CUS/CSS/DL as real GIS attributes (not something requiring
    document-table parsing, see DECISIONS.md)."""
    parcel_id = await _parcel_id(async_db_session, "101A00986003628")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    assert len(zoning.pap_nq_zones) >= 1
    match = next(
        z for z in zoning.pap_nq_zones if z.denomination == "Weimershof WH-07 - Kennedy Sud"
    )
    assert match.cos_max == pytest.approx(0.6)
    assert match.cus_max == pytest.approx(1.25)
    assert match.css_max == pytest.approx(0.8)
    assert match.dl_max == pytest.approx(115.0)
    assert match.written_document is not None
    assert "plan d’aménagement" in match.written_document.text.lower()
