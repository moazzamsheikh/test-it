"""M2 PAG/PAP zoning — real polygon data from ACT's per-commune open PAG
datasets (see DECISIONS.md and PAG_PAP_SPEC.md for the research trail).

Both tables are a *full replace scoped to their source commune* on
re-ingest, not an upsert keyed on the GML's own `gml:id` — same reasoning as
`Building` (see app/models/cadastre.py): these are government-published
polygons with no natural key we'd want to depend on across re-ingests, and
the entire zoning layer for a commune is replaced whenever the commune
publishes a new PAG version anyway.

`written_document_id`/`graphic_document_id` are resolved at ingest time
(the real DOCX/PDF filename referenced by each polygon is looked up in
`documents` once, not re-matched by string at every query) — see
ingestion/ingest_pag_zones.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import ForeignKey, Index, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PagZone(Base):
    """One real ZONAGE polygon (base PAG zone) from ACT's PAG GML export."""

    __tablename__ = "pag_zones"
    __table_args__ = (Index("ix_pag_zones_admin_commune", "admin_commune_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    admin_commune_code: Mapped[str] = mapped_column(
        ForeignKey("communes.lau2_code", ondelete="RESTRICT")
    )
    # ACT's own CATEGORIE value, e.g. "MIX_u", "FOR", "HAB_1" — a real, open
    # vocabulary (see the WMS legend cross-check in DECISIONS.md), not an enum.
    category: Mapped[str] = mapped_column(Text)
    genre: Mapped[str | None] = mapped_column(Text, default=None)
    written_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), default=None
    )
    geom: Mapped[WKBElement] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=2169))
    source_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PapQeZone(Base):
    """One real ZONES_QE polygon (PAP "Quartier Existant" sub-variant) from
    ACT's PAG GML export — a finer-grained zone within an already-built
    quarter, with its own written AND graphic document references."""

    __tablename__ = "pap_qe_zones"
    __table_args__ = (Index("ix_pap_qe_zones_admin_commune", "admin_commune_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    admin_commune_code: Mapped[str] = mapped_column(
        ForeignKey("communes.lau2_code", ondelete="RESTRICT")
    )
    written_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), default=None
    )
    # The graphic-part PDFs are large (Luxembourg City's 23 files total
    # ~250MB) and not text-extractable in a useful way yet — deliberately
    # NOT fetched/ingested as a Document this pass (see DECISIONS.md); just
    # the real filename the GML itself references, honest about the gap
    # rather than pretending it's a resolved citation.
    graphic_document_filename: Mapped[str | None] = mapped_column(Text, default=None)
    geom: Mapped[WKBElement] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=2169))
    source_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PapNqZone(Base):
    """One real NQ_PAP polygon (PAP "Nouveau Quartier" — a not-yet-built
    zone requiring its own particular development plan before construction)
    from ACT's PAG GML export.

    Unlike PAG/PAP QE's regulation text, the real planning coefficients
    (COS/CUS/CSS/DL — the numeric limits a real architect needs to compute
    buildable floor area, footprint, and unit count) are genuine GIS
    attributes here, not something that needs parsing out of a document's
    prose/tables — verified live against real Luxembourg City and Wiltz
    data (see DECISIONS.md). `css_min` doesn't exist as a field in the real
    data (only a max — there's no minimum soil-sealing requirement), so it's
    intentionally not modelled here.
    """

    __tablename__ = "pap_nq_zones"
    __table_args__ = (Index("ix_pap_nq_zones_admin_commune", "admin_commune_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    admin_commune_code: Mapped[str] = mapped_column(
        ForeignKey("communes.lau2_code", ondelete="RESTRICT")
    )
    denomination: Mapped[str | None] = mapped_column(Text, default=None)
    genre: Mapped[str | None] = mapped_column(Text, default=None)
    # COS — Coefficient d'Occupation du Sol (ground footprint ratio)
    cos_min: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    cos_max: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    # CUS — Coefficient d'Utilisation du Sol (floor area ratio)
    cus_min: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    cus_max: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    # CSS — Coefficient de Scellement du Sol (soil-sealing / imperviousness ratio)
    css_max: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    # DL — Densité de Logement (dwelling units per hectare)
    dl_min: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    dl_max: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    written_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), default=None
    )
    # The schéma directeur (master plan) written/graphic parts are real PDFs
    # per NQ project — not fetched/parsed this pass (see DECISIONS.md): the
    # coefficients above are the actual numbers a NQ project needs, already
    # real GIS attributes, so PDF text extraction isn't required to answer
    # "what are COS/CUS/CSS/DL here" — only to read the full narrative text.
    schema_directeur_filename: Mapped[str | None] = mapped_column(Text, default=None)
    schema_directeur_graphic_filename: Mapped[str | None] = mapped_column(Text, default=None)
    geom: Mapped[WKBElement] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=2169))
    source_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
