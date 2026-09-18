"""Tests for the two M1.4-brief-named overlay categories ("zone verte";
"PAP NQ / PAP QE perimeters") that aren't separate WMS layers — derived
from the real M2 PAG data instead (see DECISIONS.md). Against real ingested
parcels, not fixtures, matching the rest of this project's test style.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.services.pag_zoning import derive_m14_style_constraints, get_pag_zoning


async def _parcel_id_and_commune(
    session: AsyncSession, cadastral_id: str
) -> tuple[uuid.UUID, str | None]:
    row = (
        await session.execute(
            select(Parcel.id, Parcel.admin_commune_code).where(Parcel.cadastral_id == cadastral_id)
        )
    ).one()
    return row.id, row.admin_commune_code


async def test_for_zone_parcel_is_zone_verte(async_db_session: AsyncSession) -> None:
    """075F00184002448 ("8 Rue Beck") is a real, verified FOR (forestière)
    zone — one of the four real ACT categories grouped under "Zone verte"
    in the government's own PAG legend (see DECISIONS.md)."""
    parcel_id, admin_commune_code = await _parcel_id_and_commune(
        async_db_session, "075F00184002448"
    )
    zoning = await get_pag_zoning(async_db_session, parcel_id)
    constraints = derive_m14_style_constraints(zoning, admin_commune_code)

    by_code = {c.layer_code: c for c in constraints}
    assert by_code["zone_verte"].intersects is True
    assert by_code["zone_verte"].detail == {"categories": ["FOR"]}
    assert by_code["pap_qe_perimeter"].intersects is False
    assert by_code["pap_nq_perimeter"].intersects is False


async def test_parcel_with_real_nq_zones_shows_pap_nq_perimeter(
    async_db_session: AsyncSession,
) -> None:
    """101A00986003628 genuinely intersects several real NQ_PAP zones and a
    real ZONES_QE perimeter (see test_pag_zoning.py) — both derived
    constraints should report intersects=True with real detail."""
    parcel_id, admin_commune_code = await _parcel_id_and_commune(
        async_db_session, "101A00986003628"
    )
    zoning = await get_pag_zoning(async_db_session, parcel_id)
    constraints = derive_m14_style_constraints(zoning, admin_commune_code)

    by_code = {c.layer_code: c for c in constraints}
    assert by_code["pap_nq_perimeter"].intersects is True
    assert by_code["pap_nq_perimeter"].overlap_m2 is not None
    assert by_code["pap_nq_perimeter"].overlap_m2 > 0
    denominations = (by_code["pap_nq_perimeter"].detail or {}).get("denominations", [])
    assert isinstance(denominations, list)
    assert "Weimershof WH-07 - Kennedy Sud" in denominations
    assert by_code["pap_qe_perimeter"].intersects is True


async def test_source_url_resolves_per_commune(async_db_session: AsyncSession) -> None:
    """The derived constraints point at the real, correct per-commune
    dataset page, not a generic fallback, when the commune is known."""
    parcel_id, admin_commune_code = await _parcel_id_and_commune(
        async_db_session, "075F00184002448"
    )
    assert admin_commune_code == "0304"  # Luxembourg City
    zoning = await get_pag_zoning(async_db_session, parcel_id)
    constraints = derive_m14_style_constraints(zoning, admin_commune_code)

    assert all(
        c.source_url == "https://data.public.lu/en/datasets/pag-ville-de-luxembourg/"
        for c in constraints
    )
