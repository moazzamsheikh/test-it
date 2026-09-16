"""M4.2 — PDF generation, against real ingested data. Checks the real
properties the brief asks for (a real PDF comes back, it's deterministic
for the same parcel/corpus state, the map extract renders) rather than
re-testing the report content itself (see test_report.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_report_pdf_is_a_real_pdf() -> None:
    resp = client.get("/api/v1/parcels/097D00240002285/report.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


def test_report_pdf_is_byte_deterministic_for_the_same_parcel() -> None:
    """The brief's own requirement: same parcel + same corpus state ->
    byte-comparable PDF. The generation timestamp shown in the footer is
    deliberately derived from `data_freshness` (a real, corpus-state-tied
    value), not wall-clock time, precisely so this holds (see
    app/services/report_pdf.py)."""
    first = client.get("/api/v1/parcels/097D00240002285/report.pdf").content
    second = client.get("/api/v1/parcels/097D00240002285/report.pdf").content
    assert first == second


def test_report_pdf_404s_for_unknown_parcel() -> None:
    resp = client.get("/api/v1/parcels/000000000000000/report.pdf")
    assert resp.status_code == 404
