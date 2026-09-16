"""M2.1's required observability endpoint — real API test against real
ingested `sources` rows, not fixtures."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_source_status_reflects_real_ingested_sources() -> None:
    resp = client.get("/api/v1/sources/status")
    assert resp.status_code == 200
    sources = resp.json()
    assert len(sources) > 5

    by_name = {s["name"]: s for s in sources}
    national_law = next((s for name, s in by_name.items() if "aménagement communal" in name), None)
    assert national_law is not None
    assert national_law["last_status"] == "ok"
    assert national_law["documents_ingested"] >= 1
