"""M4.1 — the exact structured report schema named in the assessment brief
(`GET /api/v1/parcel/{cadastral_id}/report`). Assembled in
`app/services/report.py` from data that already exists (M1 parcel detail,
M2 PAG/PAP zoning, M1.4 overlays) — this module only shapes it into the
brief's own field names, it does not compute anything new itself.

Every assertion carries a source; anything undetermined is
`confidence: "not_extracted"`/`"unknown"` and surfaces in `open_questions`,
never guessed — the brief's own non-negotiable rule (Section 4.1)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.parcel import AddressSummary


class ReportParcel(BaseModel):
    id: str
    commune: str | None
    section: str
    area_m2: float
    # Null is the honest, already-established answer (see DECISIONS.md) —
    # no declared-area field exists anywhere in the real PCN source data.
    area_declared_m2: float | None
    geometry: dict[str, object]


class ReportZoning(BaseModel):
    pag_zone: str | None
    pag_zone_label: str | None
    pag_document_url: str | None
    pap_type: str | None  # "PAP QE" | "PAP NQ" | null
    pap_reference: str | None
    pap_document_url: str | None
    sectoral_plans: list[str]


class BuildingParameters(BaseModel):
    max_height_m: float | None
    max_storeys: int | None
    setback_front_m: float | None
    setback_side_m: float | None
    setback_rear_m: float | None
    max_footprint_ratio: float | None
    max_density: float | None
    extraction_confidence: str  # "high" | "medium" | "low" | "not_extracted"


class ReportConstraint(BaseModel):
    type: str
    applies: bool
    detail: str | None
    source_url: str
    confidence: str  # "high" | "medium"
    consequence: str


class ApplicableDocument(BaseModel):
    title: str
    type: str
    url: str
    date: date | None
    legal_status: str
    relevance: str


class DataFreshness(BaseModel):
    """Per real ingested source contributing to this report, its own
    `sources.last_success_at` (M2.1) — not a single blanket timestamp, since
    a parcel's PAG data and its Legilux citations are genuinely fetched at
    different times."""

    oldest_source_last_success_at: datetime | None
    newest_source_last_success_at: datetime | None
    by_document_type: dict[str, datetime | None]


class ParcelReport(BaseModel):
    parcel: ReportParcel
    addresses: list[AddressSummary]
    zoning: ReportZoning
    building_parameters: BuildingParameters
    constraints: list[ReportConstraint]
    applicable_documents: list[ApplicableDocument]
    # M5 (the decision engine that would populate this) doesn't exist yet —
    # honestly empty rather than a guessed baseline list (see DECISIONS.md).
    required_authorisations: list[str]
    open_questions: list[str]
    generated_at: datetime
    data_freshness: DataFreshness
