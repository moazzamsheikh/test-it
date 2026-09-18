"""ZPIN's dynamic per-feature document linking (Tier 2): unlike the static
Tier-1 documents, ZPIN's real `lien_legilux` GIS attribute can address ANY
of Luxembourg's real nature reserves, not just ones manually discovered near
our two target communes — see app/services/legilux_dynamic.py and
DECISIONS.md. These tests exercise the already-cached path (the real
document was ingested once, by hand, against the live Legilux page during
development — see WALKTHROUGH.md) rather than making a live network call on
every test run, matching this project's existing overlay-test style
(test_overlays.py's own comment on why: exercising a real external service
on every test run would be slow and repeatedly hit a free public server for
no reason).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.parcels import get_parcel_detail
from ingestion.legilux_extraction import eli_url_to_richtext_html_url


def test_eli_url_to_richtext_html_url_transform() -> None:
    """Pure function, no network — confirmed mechanical against 8 real
    documents this project has ingested (see DECISIONS.md), including this
    exact ZPIN example."""
    eli_url = "https://legilux.public.lu/eli/etat/leg/rgd/2024/01/24/a15/jo"
    assert eli_url_to_richtext_html_url(eli_url) == (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2024/01/24/a15/jo/fr/"
        "html/eli-etat-leg-rgd-2024-01-24-a15-jo-fr-html.html"
    )


async def test_zpin_reserve_resolves_a_real_dynamic_document(
    async_db_session: AsyncSession,
) -> None:
    """035B00891000002 genuinely intersects the real "Gréngewald" ZPIN
    reserve (verified live against the government's own WMS — see
    DECISIONS.md/WALKTHROUGH.md) — its lien_legilux attribute must resolve
    to a real ingested document, not just the raw GIS fact."""
    detail = await get_parcel_detail(async_db_session, "035B00891000002")
    assert detail is not None
    zpin = next(c for c in detail.constraints if c.layer_code == "reserves_naturelles")

    assert zpin.intersects is True
    assert zpin.detail is not None
    assert zpin.detail["nom"] == "Gréngewald"
    assert zpin.document is not None
    assert zpin.document.title is not None
    assert zpin.document.title.startswith("Règlement grand-ducal du 24 janvier 2024")
    lien_legilux = zpin.detail["lien_legilux"]
    assert isinstance(lien_legilux, str)
    assert zpin.document.source_url == eli_url_to_richtext_html_url(lien_legilux)


async def test_two_parcels_in_the_same_reserve_share_one_document(
    async_db_session: AsyncSession,
) -> None:
    """035B00891000002 and 035B00687000450 both intersect the same real
    Gréngewald reserve — the dynamic linking must resolve to the exact same
    ingested document for both, not create a duplicate."""
    first = await get_parcel_detail(async_db_session, "035B00891000002")
    second = await get_parcel_detail(async_db_session, "035B00687000450")
    assert first is not None and second is not None

    first_doc = next(c for c in first.constraints if c.layer_code == "reserves_naturelles").document
    second_doc = next(
        c for c in second.constraints if c.layer_code == "reserves_naturelles"
    ).document
    assert first_doc is not None and second_doc is not None
    assert first_doc.source_url == second_doc.source_url
