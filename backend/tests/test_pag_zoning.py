"""M2 PAG zoning tests — against the real ingested data (see
`make ingest-pag-zones`), not fixtures. Mirrors the M1.5/M1.4 approach:
real parcels, real assertions, real (sometimes surprising) results."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.models.enums import DocumentType
from app.models.provenance import Document
from app.services.pag_zoning import get_pag_zoning


async def _parcel_id(session: AsyncSession, cadastral_id: str) -> uuid.UUID:
    return (
        await session.execute(select(Parcel.id).where(Parcel.cadastral_id == cadastral_id))
    ).scalar_one()


async def test_real_parcel_resolves_to_its_current_pag_zone(
    async_db_session: AsyncSession,
) -> None:
    """075F00184002448 ("8 Rue Beck") resolves against ACT's current live
    PAG vector source, rather than the stale downloadable ZIP."""
    parcel_id = await _parcel_id(async_db_session, "075F00184002448")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    assert len(zoning.pag_zones) == 1
    match = zoning.pag_zones[0]
    assert match.category == "MIX_u"
    assert match.overlap_m2 > 0
    assert match.document is not None
    assert match.document.article_ref == "Art. 5"
    assert match.document.text is not None
    assert "mixte urbaine" in match.document.text.lower()


async def test_live_city_parcel_resolves_to_hab1_zone(async_db_session: AsyncSession) -> None:
    """075C00163000437 (38 Rue de Trèves) is shown as HAB-1 by ACT's
    current live PAG map; the assertion prevents a stale bulk publication from
    reintroducing the old FOR classification (see DECISIONS.md)."""
    parcel_id = await _parcel_id(async_db_session, "075C00163000437")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    assert len(zoning.pag_zones) == 1
    assert zoning.pag_zones[0].category == "HAB_1"
    assert zoning.pag_zones[0].overlap_m2 > 0
    assert zoning.pag_zones[0].document is not None
    assert zoning.pag_zones[0].document.article_ref == "Art. 1"


async def test_live_junglinster_parcel_resolves_to_hab2_zone(
    async_db_session: AsyncSession,
) -> None:
    """064B01784009471 (1 Rue Rham) resolves to HAB-2 in ACT's current
    live C027 PAG data, rather than the stale bulk result."""
    parcel_id = await _parcel_id(async_db_session, "064B01784009471")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    hab_zones = [zone for zone in zoning.pag_zones if zone.category == "HAB_2"]
    assert len(hab_zones) == 1
    assert hab_zones[0].overlap_m2 > 0
    assert hab_zones[0].document is not None
    assert hab_zones[0].document.article_ref == "Art. 2"


async def test_live_wiltz_parcel_resolves_to_hab1_zone(
    async_db_session: AsyncSession,
) -> None:
    """127B01405004232 (1 An der Kaul) resolves to HAB-1 in ACT's current
    live C023 PAG data."""
    parcel_id = await _parcel_id(async_db_session, "127B01405004232")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    hab_zones = [zone for zone in zoning.pag_zones if zone.category == "HAB_1"]
    assert len(hab_zones) == 1
    assert hab_zones[0].overlap_m2 > 0
    assert hab_zones[0].document is not None
    assert hab_zones[0].document.article_ref == "Art. 3"


async def test_live_pag_source_fills_former_bulk_export_coverage_gap(
    async_db_session: AsyncSession,
) -> None:
    """054A00396005426 is covered by current live PAG data even though the
    older downloadable export returned no zone."""
    parcel_id = await _parcel_id(async_db_session, "054A00396005426")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    assert {zone.category for zone in zoning.pag_zones} == {"AGR", "VERD"}
    assert all(zone.overlap_m2 > 0 for zone in zoning.pag_zones)


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
    assert match.written_document.text is not None
    assert "plan d’aménagement" in match.written_document.text.lower()


async def test_live_schengen_parcel_resolves_current_pag_zone(
    async_db_session: AsyncSession,
) -> None:
    """097D00240002285 (Schengen) resolves against the current live PAG
    vector source; the older ZIP's PAP-QE overlap is no longer present."""
    parcel_id = await _parcel_id(async_db_session, "097D00240002285")
    zoning = await get_pag_zoning(async_db_session, parcel_id)

    assert len(zoning.pag_zones) == 1
    assert zoning.pag_zones[0].category == "MIX_v"
    assert zoning.pag_zones[0].overlap_m2 > 0


async def test_pag_written_and_graphic_documents_all_carry_a_commune_code(
    async_db_session: AsyncSession,
) -> None:
    """Real, live-discovered M2 bug (found while building M3's chat
    retrieval, fixed in ingestion/ingest_pag_zones.py — see DECISIONS.md):
    `_get_or_create_written_document`/`_get_or_create_graphic_document`
    never set `commune_code`, despite `admin_commune_code` being available
    at every call site. Silent effect since M2: a query scoped to one
    commune could retrieve another commune's PAP QE/NQ written-part text —
    exactly the cross-commune leakage M3.1 explicitly says must not
    happen. This asserts the fix generalises across the real corpus, not
    just the one parcel other tests in this file happen to check."""
    rows = (
        await async_db_session.execute(
            select(Document.title, Document.commune_code).where(
                Document.document_type.in_([DocumentType.pag_written, DocumentType.pag_graphic])
            )
        )
    ).all()

    assert len(rows) > 0  # would trivially "pass" on an empty corpus otherwise
    missing = [title for title, commune_code in rows if commune_code is None]
    assert missing == []
