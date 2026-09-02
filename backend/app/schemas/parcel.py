"""Pydantic response models for the parcel identify / detail API (M1.3)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class AddressSummary(BaseModel):
    id: uuid.UUID
    street_name: str
    house_number: str
    locality: str | None


class BuildingSummary(BaseModel):
    id: uuid.UUID
    occupation_code: int | None
    occupation_label: str | None
    overlap_m2: float


class OverlayConstraint(BaseModel):
    """One M1.4 regulatory overlay's result for this parcel — intersects
    yes/no, the intersecting feature's own attributes (whatever that layer
    carries), a source URL, and the exact overlap area when we found a real
    hit (see app/services/overlays.py for why "found a hit" is a sampled
    approximation but the area itself, once found, is exact)."""

    layer_code: str
    label: str
    category: str
    intersects: bool
    overlap_m2: float | None
    detail: dict[str, object] | None
    source_url: str


class ParcelSummary(BaseModel):
    """Minimal shape returned by identify-by-point and by-reference search —
    enough to let the caller pick one, then fetch full detail by cadastral_id."""

    cadastral_id: str
    cadastral_commune_code: str
    cadastral_commune_name: str
    admin_commune_code: str | None
    admin_commune_name: str | None
    section_code: str
    numero_principal: int
    numero_secondaire: int
    area_geom_m2: float


class ParcelDetail(ParcelSummary):
    """Full side-panel payload for a selected parcel (M1.3)."""

    lieudit: str | None
    nature_code: int | None
    nature_label: str | None
    # No source found yet for a declared/legal area (see DECISIONS.md) —
    # returned as null rather than fabricated.
    area_declared_m2: float | None
    addresses: list[AddressSummary]
    buildings: list[BuildingSummary]
    constraints: list[OverlayConstraint]
    geometry_wgs84_geojson: dict[str, object]


class ParcelIdentifyResponse(BaseModel):
    """Response for the click-to-identify endpoint. A list, not a single
    parcel: a click can miss every parcel (0 results, e.g. a road), or land
    on a boundary shared by two parcels (>1 result) — both are real, honest
    outcomes, not something to silently resolve by picking one (M1.3 edge
    cases: "a click exactly on a boundary")."""

    parcels: list[ParcelSummary]
