"""Tier-1 overlay-document citations: layers governed by a single real
règlement grand-ducal (PSL/PST/PSZAE/PSP, and the Findel airport servitude
RGD — see app/overlay_layers.py's `document_url` and
ingestion/ingest_overlay_documents.py) must resolve a real document citation
on every parcel's constraint list, intersecting or not — the RGD applies to
the whole layer, not just the intersecting feature. Layers with no
`document_url` set must keep returning `document: None`, same as before
this feature existed.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.parcels import get_parcel_detail


async def test_tier1_layers_carry_a_real_document_citation(
    async_db_session: AsyncSession,
) -> None:
    detail = await get_parcel_detail(async_db_session, "075F00184002448")
    assert detail is not None
    by_code = {c.layer_code: c for c in detail.constraints}

    for code in ("psl", "pst", "pszae", "psp"):
        document = by_code[code].document
        assert document is not None, f"{code} should carry a real ingested document citation"
        assert document.title.startswith("Règlement grand-ducal du 10 février 2021")
        assert document.source_url.startswith("https://data.legilux.public.lu/")
        # Multi-article documents show only the document-level citation (see
        # app/services/documents.py) — not one of the 8-16 real articles.
        assert document.article_ref is None
        assert document.text is None


async def test_findel_servitude_carries_a_real_document_citation(
    async_db_session: AsyncSession,
) -> None:
    """A separate RGD (17 May 2006, POS "Aéroport et environs") from the four
    sectoral plans above — different year, different document, same Legilux
    richtext structure, confirming the extractor generalises rather than
    happening to work for one document family."""
    detail = await get_parcel_detail(async_db_session, "075F00184002448")
    assert detail is not None
    by_code = {c.layer_code: c for c in detail.constraints}

    document = by_code["findel_servitude"].document
    assert document is not None
    assert document.title.startswith("Règlement grand-ducal du 17 mai 2006")
    assert document.source_url.startswith("https://data.legilux.public.lu/")
    assert document.article_ref is None
    assert document.text is None


async def test_layers_without_a_document_url_stay_none(async_db_session: AsyncSession) -> None:
    detail = await get_parcel_detail(async_db_session, "075F00184002448")
    assert detail is not None
    by_code = {c.layer_code: c for c in detail.constraints}

    assert by_code["pag_zoning"].document is None
    assert by_code["pos"].document is None


async def test_flood_zones_resolve_the_correct_per_commune_rgd(
    async_db_session: AsyncSession,
) -> None:
    """Flood HQ20/HQ100 aren't governed by one national document — a real,
    separate RGD exists per river basin (see DECISIONS.md: the original
    "one PGRI document" assumption was wrong). Luxembourg City (075F...,
    on the Alzette) and Wiltz (041C..., on the Wiltz river) must each
    resolve to their own, different, correctly-matched RGD via
    `OverlayLayer.document_url_by_commune`."""
    lux_city = await get_parcel_detail(async_db_session, "075F00184002448")
    wiltz = await get_parcel_detail(async_db_session, "041C00009003200")
    assert lux_city is not None
    assert wiltz is not None

    for detail, expected_watercourse in (
        (lux_city, "cours d’eau de l’Alzette"),
        (wiltz, "cours d’eau de la Sûre"),
    ):
        by_code = {c.layer_code: c for c in detail.constraints}
        for code in ("flood_hq20", "flood_hq100"):
            document = by_code[code].document
            assert document is not None, f"{code} should carry a real per-commune document"
            assert expected_watercourse in document.title

    # The two communes must resolve to genuinely different documents, not
    # the same one by accident.
    lux_doc = next(c for c in lux_city.constraints if c.layer_code == "flood_hq20").document
    wiltz_doc = next(c for c in wiltz.constraints if c.layer_code == "flood_hq20").document
    assert lux_doc is not None and wiltz_doc is not None
    assert lux_doc.source_url != wiltz_doc.source_url
