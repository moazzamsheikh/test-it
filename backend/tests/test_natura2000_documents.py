"""Tier-2 Natura 2000 static SITECODE->document linking: unlike ZPIN, real
Natura 2000 features only carry a SITECODE/SITENAME (no direct Legilux
link — verified live, see DECISIONS.md), so each real site intersecting our
two target communes is mapped by hand in
`app/overlay_layers.py::_NATURA2000_HABITATS_DOCUMENT_URLS` /
`_NATURA2000_BIRDS_DOCUMENT_URLS`, ingested by the same batch script as
Tier 1. Against real ingested parcels, not fixtures — each cadastral_id
below was found by probing the live government WMS and confirmed to
genuinely intersect the named real site (see WALKTHROUGH.md).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.parcels import get_parcel_detail


async def test_habitats_site_in_luxembourg_city_resolves_real_document(
    async_db_session: AsyncSession,
) -> None:
    """101A00987004029 genuinely intersects the real "Vallée de la Mamer et
    de l'Eisch" habitats site (LU0001018)."""
    detail = await get_parcel_detail(async_db_session, "101A00987004029")
    assert detail is not None
    habitats = next(c for c in detail.constraints if c.layer_code == "natura2000_habitats")

    assert habitats.intersects is True
    assert habitats.detail is not None
    assert habitats.detail["SITECODE"] == "LU0001018"
    assert habitats.document is not None
    assert habitats.document.title.startswith("Règlement grand-ducal du 13 juin 2025")
    assert "Mamer" in habitats.document.title


async def test_habitats_site_in_wiltz_resolves_a_different_real_document(
    async_db_session: AsyncSession,
) -> None:
    """127D00529001499 genuinely intersects the real "Vallées de la Sûre, de
    la Wiltz, de la Clerve et du Lellgerbaach" habitats site (LU0001006) —
    proves per-site resolution works in both target communes, not just one."""
    detail = await get_parcel_detail(async_db_session, "127D00529001499")
    assert detail is not None
    habitats = next(c for c in detail.constraints if c.layer_code == "natura2000_habitats")

    assert habitats.intersects is True
    assert habitats.detail is not None
    assert habitats.detail["SITECODE"] == "LU0001006"
    assert habitats.document is not None
    assert habitats.document.title.startswith("Règlement grand-ducal du 24 mai 2023")


async def test_one_parcel_can_resolve_both_habitats_and_birds_sites(
    async_db_session: AsyncSession,
) -> None:
    """061E00405001802 genuinely intersects both a real habitats site
    (LU0001026, "Bertrange - Greivelserhaff / Bouferterhaff") and a real
    birds site (LU0002017, "Région du Lias moyen") — the two Natura 2000
    layers resolve independently, each via its own static SITECODE table."""
    detail = await get_parcel_detail(async_db_session, "061E00405001802")
    assert detail is not None
    by_code = {c.layer_code: c for c in detail.constraints}

    habitats = by_code["natura2000_habitats"]
    assert habitats.intersects is True
    assert habitats.detail is not None
    assert habitats.detail["SITECODE"] == "LU0001026"
    assert habitats.document is not None
    assert "Bertrange" in habitats.document.title

    birds = by_code["natura2000_oiseaux"]
    assert birds.intersects is True
    assert birds.detail is not None
    assert birds.detail["SITECODE"] == "LU0002017"
    assert birds.document is not None
    assert "Lias moyen" in birds.document.title
