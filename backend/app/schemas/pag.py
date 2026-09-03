"""M2 PAG/PAP zoning response schema (see DECISIONS.md / PAG_PAP_SPEC.md)."""

from __future__ import annotations

from pydantic import BaseModel


class DocumentReference(BaseModel):
    title: str
    source_url: str
    article_ref: str | None
    # The real, verbatim regulation text — null only if the referenced
    # document couldn't be resolved (an honest gap, not expected in practice
    # once ingestion has run for a commune).
    text: str | None


class PagZoneMatch(BaseModel):
    """One real ZONAGE polygon intersecting the parcel. `category`/`genre`
    are ACT's own real values (e.g. "MIX_u", "FOR") — reported exactly as
    the real data says, including surprising ones (see DECISIONS.md)."""

    category: str
    genre: str | None
    overlap_m2: float
    document: DocumentReference | None


class PapQeZoneMatch(BaseModel):
    """One real ZONES_QE polygon (PAP "Quartier Existant" sub-zone)
    intersecting the parcel. `graphic_document_filename` is a real filename
    reference only — its content isn't ingested yet (see DECISIONS.md)."""

    overlap_m2: float
    written_document: DocumentReference | None
    graphic_document_filename: str | None


class PagZoningInfo(BaseModel):
    pag_zones: list[PagZoneMatch]
    pap_qe_zones: list[PapQeZoneMatch]
