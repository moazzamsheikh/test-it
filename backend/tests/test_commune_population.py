"""M2.4 commune population — real LUSTAT/STATEC data, not a fixture."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Commune


async def test_all_communes_have_a_real_population(async_db_session: AsyncSession) -> None:
    total = (await async_db_session.execute(select(func.count()).select_from(Commune))).scalar_one()
    with_population = (
        await async_db_session.execute(
            select(func.count()).select_from(Commune).where(Commune.population.is_not(None))
        )
    ).scalar_one()
    assert with_population == total


async def test_luxembourg_city_population_is_plausible(async_db_session: AsyncSession) -> None:
    """A loose sanity bound, not an exact figure (population changes every
    year) — Luxembourg City is the largest commune, real figure ~130k."""
    luxembourg = (
        await async_db_session.execute(select(Commune).where(Commune.name == "Luxembourg"))
    ).scalar_one()
    assert luxembourg.population is not None
    assert 100_000 < luxembourg.population < 200_000
