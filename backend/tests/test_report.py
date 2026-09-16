"""M4.1 — the structured parcel report, against real ingested data, not
fixtures. `build_parcel_report` reshapes data already covered by
`test_pag_zoning.py`/`test_real_data.py` into the brief's exact schema; these
tests check the reshaping itself (label derivation, PAP QE/NQ precedence,
honest gaps), not the underlying zoning/overlay logic a second time."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.services.report import build_parcel_report

client = TestClient(app)


async def test_real_schengen_parcel_report_derives_a_human_zone_label(
    async_db_session: AsyncSession,
) -> None:
    """097D00240002285's real written-part document uses parentheses around
    the zone code ("Zone mixte villageoise (MIX–v)"), not the square
    brackets most other communes use — a real, live-discovered format
    difference the label extraction must handle generically (see
    DECISIONS.md)."""
    report = await build_parcel_report(async_db_session, "097D00240002285")
    assert report is not None
    assert report.zoning.pag_zone == "MIX_v"
    assert report.zoning.pag_zone_label == "mixte villageoise"
    assert report.zoning.pap_type == "PAP QE"
    assert report.zoning.pap_reference == "113_QE_Schengen"
    assert report.parcel.area_declared_m2 is None  # honest gap, never fabricated


async def test_real_nq_parcel_reports_real_coefficients_with_partial_confidence(
    async_db_session: AsyncSession,
) -> None:
    """101A00986003628 intersects both a PAP QE zone and a real PAP NQ zone
    (Weimershof) simultaneously — a genuine overlap, not a bug (see
    DECISIONS.md). The flat `pap_type` field can only report one, but the
    NQ zone's real COS/CUS/CSS/DL GIS attributes still surface correctly in
    building_parameters, with height/storeys/setbacks honestly null."""
    report = await build_parcel_report(async_db_session, "101A00986003628")
    assert report is not None
    assert report.zoning.pap_type == "PAP QE"
    assert any("both a PAP Quartier Existant" in q for q in report.open_questions)

    bp = report.building_parameters
    assert bp.max_footprint_ratio is not None
    assert bp.max_density is not None
    assert bp.max_height_m is None
    assert bp.extraction_confidence == "medium"


async def test_required_authorisations_is_honestly_empty(async_db_session: AsyncSession) -> None:
    """M5 (the decision engine that would populate this) doesn't exist yet
    — an empty list plus an open_questions entry is the honest answer, not
    a fabricated baseline (see DECISIONS.md)."""
    report = await build_parcel_report(async_db_session, "097D00240002285")
    assert report is not None
    assert report.required_authorisations == []
    assert any("M5 decision engine" in q for q in report.open_questions)


async def test_applicable_documents_are_deduplicated_and_carry_real_metadata(
    async_db_session: AsyncSession,
) -> None:
    report = await build_parcel_report(async_db_session, "097D00240002285")
    assert report is not None
    urls = [d.url for d in report.applicable_documents]
    assert len(urls) == len(set(urls))  # no duplicate documents
    assert all(d.type for d in report.applicable_documents)
    assert all(d.legal_status for d in report.applicable_documents)


def test_report_api_returns_the_real_schema() -> None:
    resp = client.get("/api/v1/parcels/097D00240002285/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parcel"]["id"] == "097D00240002285"
    assert body["zoning"]["pag_zone"] == "MIX_v"
    assert "generated_at" in body
    assert "data_freshness" in body


def test_report_api_404s_for_unknown_parcel() -> None:
    resp = client.get("/api/v1/parcels/000000000000000/report")
    assert resp.status_code == 404
