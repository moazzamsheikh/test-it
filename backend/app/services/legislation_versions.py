"""M2.4 bonus — resolves which real Legilux version of a law was in force
on a given date, from the SPARQL-derived `legislation_versions` table
(`ingestion/ingest_legislation_versions.py`).

Windows are contiguous by construction (each real consolidation's validity
starts where the previous one ended), so "most recent version whose start
date is on/before the target date" is sufficient on its own — no need to
also check `date_end_applicability`, which is absent for the current version
of every law by definition (see that module's docstring for the real
`dateApplicability`/`dateEntryInForce` fallback this relies on)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import LegislationVersion


async def get_version_in_force(
    session: AsyncSession, work_eli: str, on_date: date
) -> LegislationVersion | None:
    stmt = (
        select(LegislationVersion)
        .where(
            LegislationVersion.work_eli == work_eli,
            LegislationVersion.date_applicability <= on_date,
        )
        .order_by(LegislationVersion.date_applicability.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_versions(session: AsyncSession, work_eli: str) -> list[LegislationVersion]:
    stmt = (
        select(LegislationVersion)
        .where(LegislationVersion.work_eli == work_eli)
        .order_by(LegislationVersion.date_applicability)
    )
    return list((await session.execute(stmt)).scalars().all())
