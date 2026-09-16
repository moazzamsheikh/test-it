"""Tier 3 (water protection) and Tier 4 (POS) items that turned out to
carry the same kind of direct per-feature Legilux link ZPIN does, once
actually checked live rather than assumed from the earlier research pass —
see DECISIONS.md. Both reuse `app/services/legilux_dynamic.py` unchanged,
via `OverlayLayer.document_url_detail_key`. Against real ingested parcels,
not fixtures — each cadastral_id was found by probing the live government
WMS and confirmed to genuinely intersect the named real zone.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.parcels import get_parcel_detail


async def test_water_protection_zone_resolves_a_real_dynamic_document(
    async_db_session: AsyncSession,
) -> None:
    """101A00987004029 genuinely intersects a real drinking-water protection
    zone around the "Siweburen" catchments. The government's own attribute
    name for the Legilux link is itself missing a trailing "l"
    ("grand-duca", not "grand-ducal") — a real, verified quirk of the
    source data, not a typo in this codebase."""
    detail = await get_parcel_detail(async_db_session, "101A00987004029")
    assert detail is not None
    water = next(c for c in detail.constraints if c.layer_code == "water_protection")

    assert water.intersects is True
    assert water.detail is not None
    assert water.detail["Publication du règlement grand-duca"].startswith(
        "http://legilux.public.lu/eli/etat/leg/rgd/2019/05/16/a342/jo"
    )
    assert water.document is not None
    assert water.document.title.startswith("Règlement grand-ducal du 16 mai 2019")
    assert water.document.source_url.startswith("https://data.legilux.public.lu/")


async def test_pos_perimeter_resolves_the_real_amending_rgd(
    async_db_session: AsyncSession,
) -> None:
    """054A00380006884 genuinely intersects the real POS "Aéroport et
    environs" perimeter. This layer's own real attribute (`LienMemori`)
    points at a LATER amending RGD (19 October 2020) — a different real
    document from the original 17 May 2006 RGD the separate
    `findel_servitude` layer statically cites (see DECISIONS.md) — both
    are genuinely correct citations for their own distinct WMS layers."""
    detail = await get_parcel_detail(async_db_session, "054A00380006884")
    assert detail is not None
    pos = next(c for c in detail.constraints if c.layer_code == "pos")

    assert pos.intersects is True
    assert pos.detail is not None
    assert pos.detail["NomProjet"] == "Plan d'occupation du sol «Aéroport et environs»"
    assert pos.document is not None
    assert pos.document.title.startswith("Règlement grand-ducal du 19 octobre 2020")
