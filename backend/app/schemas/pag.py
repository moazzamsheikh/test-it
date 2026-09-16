"""M2 PAG/PAP zoning response schema (see DECISIONS.md / PAG_PAP_SPEC.md)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class DocumentReference(BaseModel):
    title: str
    source_url: str
    article_ref: str | None
    # The real, verbatim regulation text — null for a graphic/map document
    # (nothing meaningful to extract) or if the referenced document
    # couldn't be resolved (an honest gap, not expected in practice once
    # ingestion has run for a commune).
    text: str | None
    # Set only when we actually stored the real file locally (graphic PDFs
    # — see ingestion/ingest_pag_zones.py) — lets a client build a real
    # `GET /api/v1/documents/{document_id}/file` download link rather than
    # just knowing a document exists.
    document_id: uuid.UUID | None = None


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
    intersecting the parcel. `graphic_document` is the real stored map PDF
    (see DECISIONS.md) when it was found in the source ZIP;
    `graphic_document_filename` is the raw filename either way."""

    overlap_m2: float
    written_document: DocumentReference | None
    graphic_document_filename: str | None
    graphic_document: DocumentReference | None


class PapNqZoneMatch(BaseModel):
    """One real NQ_PAP polygon (PAP "Nouveau Quartier" — not yet built)
    intersecting the parcel. COS/CUS/CSS/DL are real GIS attributes, not
    parsed from document text — verified live for both target communes
    (see DECISIONS.md). `css_min` doesn't exist in the real data (only a
    max), so there's no field for it. The schéma-directeur's written PDF
    remains a filename reference only; its graphic (map) part is fetched
    and stored like PAP QE's — see `schema_directeur_graphic_document`."""

    denomination: str | None
    genre: str | None
    cos_min: float | None
    cos_max: float | None
    cus_min: float | None
    cus_max: float | None
    css_max: float | None
    dl_min: float | None
    dl_max: float | None
    overlap_m2: float
    written_document: DocumentReference | None
    schema_directeur_filename: str | None
    schema_directeur_graphic_filename: str | None
    schema_directeur_graphic_document: DocumentReference | None


class PagZoningInfo(BaseModel):
    pag_zones: list[PagZoneMatch]
    pap_qe_zones: list[PapQeZoneMatch]
    pap_nq_zones: list[PapNqZoneMatch]
