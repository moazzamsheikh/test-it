"""M2.4 commune registry — real official website URLs for all real
communes, sourced from SYVICOL's own directory (`make ingest-commune-registry`)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Commune


async def test_all_communes_have_a_real_website_url(async_db_session: AsyncSession) -> None:
    total = (await async_db_session.execute(select(func.count()).select_from(Commune))).scalar_one()
    with_url = (
        await async_db_session.execute(
            select(func.count()).select_from(Commune).where(Commune.website_url.is_not(None))
        )
    ).scalar_one()
    assert with_url == total


async def test_wiltz_and_luxembourg_city_have_the_real_expected_urls(
    async_db_session: AsyncSession,
) -> None:
    wiltz = (
        await async_db_session.execute(select(Commune).where(Commune.name == "Wiltz"))
    ).scalar_one()
    assert wiltz.website_url is not None
    assert "wiltz.lu" in wiltz.website_url

    luxembourg = (
        await async_db_session.execute(select(Commune).where(Commune.name == "Luxembourg"))
    ).scalar_one()
    assert luxembourg.website_url is not None
    assert "vdl.lu" in luxembourg.website_url
