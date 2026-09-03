"""M5 procedure service test — against the real ingested document (see
`make ingest-procedures`), not a fixture row. If this fails with "no
procedure ingested yet", run that command first (same pattern as the M1
real-data tests depending on `make ingest`).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.procedures import get_building_permit_procedure


async def test_returns_the_real_ingested_building_permit_procedure(
    async_db_session: AsyncSession,
) -> None:
    procedure = await get_building_permit_procedure(async_db_session)

    assert procedure is not None
    assert "autorisation de bâtir" in procedure.title.lower()
    assert procedure.source_url.startswith("https://guichet.public.lu/")
    assert len(procedure.sections) == 6
    assert len(procedure.legal_references) == 5
    assert all(
        ref.url.startswith("http://legilux.public.lu/") for ref in procedure.legal_references
    )
