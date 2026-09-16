"""M2.4 bonus — SPARQL-based amendment-chain resolution, against the real
ingested `legislation_versions` rows (`make ingest-legislation-versions`),
not fixtures.

The real ACDU law (loi du 19 juillet 2004) is used as the concrete example
throughout: real Legilux data gives it 5 real windows — the original "jo"
text (2004-08-08 onward) plus 4 real consolidations (2021-01-01, 2023-10-01,
2024-11-11, 2025-07-22 onward) — verified live against the SPARQL endpoint
before this test was written (see DECISIONS.md).
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.provenance import Document, LegislationVersion
from app.services.legislation_versions import get_version_in_force, list_versions
from ingestion.ingest_national_legislation import NATIONAL_LAWS
from ingestion.legilux_eli import work_eli_from_filestore_url

client = TestClient(app)

_ACDU_WORK_ELI = work_eli_from_filestore_url(
    next(e for e in NATIONAL_LAWS if e.key == "acdu_2004").url
)


async def test_every_national_law_has_real_versions_ingested(
    async_db_session: AsyncSession,
) -> None:
    for entry in NATIONAL_LAWS:
        work_eli = work_eli_from_filestore_url(entry.url)
        versions = await list_versions(async_db_session, work_eli)
        assert versions, f"{entry.key} ({work_eli}) should have real SPARQL version windows"


async def test_acdu_2004_resolves_to_the_real_consolidation_in_force_on_a_date(
    async_db_session: AsyncSession,
) -> None:
    version = await get_version_in_force(async_db_session, _ACDU_WORK_ELI, date(2024, 1, 1))
    assert version is not None
    assert version.version_eli.endswith("/consolide/20231001")
    assert version.date_applicability == date(2023, 10, 1)
    assert version.date_end_applicability == date(2024, 11, 11)


async def test_acdu_2004_current_version_is_linked_to_our_own_ingested_document(
    async_db_session: AsyncSession,
) -> None:
    """The real, currently-applicable consolidation should resolve to a
    version we actually ingested full text for — not just a metadata row."""
    version = await get_version_in_force(async_db_session, _ACDU_WORK_ELI, date.today())
    assert version is not None
    assert version.in_force_status == "applicable"

    matched = (
        await async_db_session.execute(
            select(LegislationVersion).where(
                LegislationVersion.work_eli == _ACDU_WORK_ELI,
                LegislationVersion.document_id.is_not(None),
            )
        )
    ).scalar_one_or_none()
    assert matched is not None
    document = (
        await async_db_session.execute(select(Document).where(Document.id == matched.document_id))
    ).scalar_one()
    assert document.eli == matched.version_eli


async def test_no_version_before_the_laws_real_entry_into_force(
    async_db_session: AsyncSession,
) -> None:
    version = await get_version_in_force(async_db_session, _ACDU_WORK_ELI, date(1990, 1, 1))
    assert version is None


def test_version_at_api_returns_the_real_consolidation() -> None:
    resp = client.get(
        "/api/v1/legislation/version-at",
        params={"work_eli": _ACDU_WORK_ELI, "on_date": "2024-01-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version_eli"].endswith("/consolide/20231001")
    assert body["document_id"] is not None


def test_version_at_api_404s_before_the_law_existed() -> None:
    resp = client.get(
        "/api/v1/legislation/version-at",
        params={"work_eli": _ACDU_WORK_ELI, "on_date": "1990-01-01"},
    )
    assert resp.status_code == 404
