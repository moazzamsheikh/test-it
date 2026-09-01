"""API-level tests: real HTTP requests (via TestClient) against real ingested
data. Complements test_real_data.py (which tests the service/DB layer
directly) by proving the same facts are reachable through the actual HTTP
surface — routing, query parsing, response schemas included.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_address_search_finds_real_address() -> None:
    resp = client.get("/api/v1/addresses/search", params={"q": "Rue Dominique Lang"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) > 0
    assert any(r["street_name"] == "Rue Dominique Lang" for r in results)


def test_address_search_tolerates_typo_and_abbreviation() -> None:
    """ "r." (abbreviation for rue) + "Lng" (typo for Lang) — both handled at once."""
    resp = client.get("/api/v1/addresses/search", params={"q": "r. Dominique Lng"})
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["street_name"] == "Rue Dominique Lang" for r in results)


def test_parcel_identify_by_point_hits_real_parcel() -> None:
    # Real coordinates of "12 Rue Dominique Lang" -> its real parcel.
    resp = client.get(
        "/api/v1/parcels/identify",
        params={"lon": 6.173833635789299, "lat": 49.619564350815125},
    )
    assert resp.status_code == 200
    parcels = resp.json()["parcels"]
    assert any(p["cadastral_id"] == "054A00242005292" for p in parcels)


def test_parcel_identify_miss_returns_empty_list() -> None:
    """A click that lands on no parcel is a real, honest outcome — not an error."""
    resp = client.get("/api/v1/parcels/identify", params={"lon": 6.0, "lat": 49.7})
    assert resp.status_code == 200
    assert resp.json()["parcels"] == []


def test_parcel_by_reference() -> None:
    resp = client.get(
        "/api/v1/parcels/by-reference",
        params={
            "cadastral_commune_code": "054",
            "section_code": "A",
            "numero_principal": 242,
            "numero_secondaire": 5292,
        },
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["cadastral_id"] == "054A00242005292"


def test_parcel_detail_zero_address_parcel() -> None:
    """The M1.3 "zero addresses" edge case, through the real API."""
    resp = client.get("/api/v1/parcels/127B00746005379")
    assert resp.status_code == 200
    body = resp.json()
    assert body["addresses"] == []
    assert body["buildings"] == []
    assert body["area_declared_m2"] is None  # honestly null — see DECISIONS.md


def test_parcel_detail_not_found_is_404() -> None:
    resp = client.get("/api/v1/parcels/999Z99999999999")
    assert resp.status_code == 404
