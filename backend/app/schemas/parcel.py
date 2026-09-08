"""Pydantic response models for the parcel identify / detail API (M1.3)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.schemas.pag import DocumentReference, PagZoningInfo


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
    # Real ingested règlement grand-ducal text this layer is governed by
    # (only set for layers with a single applicable document — see
    # app/overlay_layers.py's `document_url` and DECISIONS.md).
    document: DocumentReference | None = None


class NeighbourDistance(BaseModel):
    """M1.5 — a nearby non-road parcel and the true minimum distance between
    the two parcels' boundaries (0.0 when they actually share an edge)."""

    cadastral_id: str
    distance_m: float


class BuildableEnvelope(BaseModel):
    """M1.5 — parcel polygon minus a manually-entered uniform setback (PAG/PAP
    setback values aren't reliably extractable yet, see DECISIONS.md).
    `geometry_wgs84_geojson` is null when the setback fully erodes the
    parcel — a real, expected outcome, not an error."""

    setback_m: float
    envelope_area_m2: float
    is_empty: bool
    geometry_wgs84_geojson: dict[str, object] | None


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
    # M1.5 — road frontage (0.0 is a real, honest result: landlocked, no
    # direct road access) and nearby non-road parcels with true distances.
    frontage_m: float
    neighbours: list[NeighbourDistance]
    # M2 — real PAG/PAP zoning from ACT's actual per-commune open data (see
    # PAG_PAP_SPEC.md), not the M1.4 WMS point-sample (which has no
    # classification attribute at all — see DECISIONS.md). Reported exactly
    # as the real data says, including surprising results.
    pag_zoning: PagZoningInfo
    geometry_wgs84_geojson: dict[str, object]


class ParcelIdentifyResponse(BaseModel):
    """Response for the click-to-identify endpoint. A list, not a single
    parcel: a click can miss every parcel (0 results, e.g. a road), or land
    on a boundary shared by two parcels (>1 result) — both are real, honest
    outcomes, not something to silently resolve by picking one (M1.3 edge
    cases: "a click exactly on a boundary")."""

    parcels: list[ParcelSummary]
