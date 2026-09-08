"""Tier-1 overlay-document citations: layers governed by a single real
règlement grand-ducal (PSL/PST/PSZAE/PSP — see app/overlay_layers.py's
`document_url` and ingestion/ingest_overlay_documents.py) must resolve a real
document citation on every parcel's constraint list, intersecting or not —
the RGD applies to the whole layer, not just the intersecting feature.
Layers with no `document_url` set must keep returning `document: None`,
same as before this feature existed.
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


async def test_layers_without_a_document_url_stay_none(async_db_session: AsyncSession) -> None:
    detail = await get_parcel_detail(async_db_session, "075F00184002448")
    assert detail is not None
    by_code = {c.layer_code: c for c in detail.constraints}

    assert by_code["pag_zoning"].document is None
    assert by_code["pos"].document is None
