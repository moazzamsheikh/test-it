"""M1 spatial schema: communes, cadastral reference data, parcels, buildings, addresses.

Design notes (see DECISIONS.md):
- Parcels carry TWO commune codes: `cadastral_commune_code` (ACT's own PCN
  numbering) and `admin_commune_code` (LAU2). These are verified to be
  different, non-1:1 numbering systems — conflating them would misattribute
  regulatory documents for any post-merger commune.
- Building<->parcel is a persisted many-to-many join (`ParcelBuilding`), not a
  FK on `Building` — real BATIMENTS source data has no parcel FK at all, and a
  building can genuinely span two parcels.
- `parcel_natures` / `building_natures` are reference tables, not enums — they
  are ACT-owned open vocabularies, not a small closed set we control.
- `area_declared_m2` has no source yet (PCN carries no such field) and is
  intentionally nullable — never fabricated.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    Computed,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Commune(Base):
    """Administrative commune (LAU2-keyed) — the regulatory-scope entity."""

    __tablename__ = "communes"

    lau2_code: Mapped[str] = mapped_column(String(4), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    canton: Mapped[str | None] = mapped_column(Text, default=None)
    district: Mapped[str | None] = mapped_column(Text, default=None)
    circonscription_electorale: Mapped[str | None] = mapped_column(Text, default=None)
    arrondissement_judiciaire: Mapped[str | None] = mapped_column(Text, default=None)
    surface_m2: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    # Populated in a later pass from limadmin-shp.zip; nullable until then.
    geom: Mapped[WKBElement | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=2169), default=None
    )


class CadastralCommune(Base):
    """ACT's own cadastral commune numbering — NOT the same as LAU2 (see DECISIONS.md)."""

    __tablename__ = "cadastral_communes"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    # Resolved via the liste-communes-sections.csv crosswalk at seed time.
    # Nullable so an unmatched name is an honest gap, not a guess.
    admin_commune_code: Mapped[str | None] = mapped_column(
        ForeignKey("communes.lau2_code", ondelete="SET NULL"), default=None
    )

    sections: Mapped[list[CadastralSection]] = relationship(back_populates="cadastral_commune")


class CadastralSection(Base):
    """Section reference data (code + display name) within a cadastral commune."""

    __tablename__ = "cadastral_sections"
    __table_args__ = (UniqueConstraint("cadastral_commune_code", "section_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cadastral_commune_code: Mapped[str] = mapped_column(
        ForeignKey("cadastral_communes.code", ondelete="CASCADE")
    )
    # Verified against real data (not the 1-2 char PARCELLES.dbf sample): Luxembourg
    # City's own crosswalk uses 3-char codes (e.g. "HaA", "HoC" for Hamm/Hollerich
    # sub-sections). See DECISIONS.md/WALKTHROUGH.md — the raw PCN shapefile field
    # is declared only 1 char wide, an unresolved inconsistency to verify once real
    # Luxembourg City parcels are ingested.
    section_code: Mapped[str] = mapped_column(String(3))
    name: Mapped[str | None] = mapped_column(Text, default=None)

    cadastral_commune: Mapped[CadastralCommune] = relationship(back_populates="sections")


class ParcelNature(Base):
    """ACT's CODE_NATURE taxonomy (~50 values) — reference table, not an enum."""

    __tablename__ = "parcel_natures"

    code: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)


class BuildingNature(Base):
    """ACT's CODE_OCCUPATION taxonomy (~34 values) — reference table, not an enum."""

    __tablename__ = "building_natures"

    code: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)


class Parcel(Base):
    """A cadastral parcel from the PCN. Geometry is authoritative; LIEUDIT/nature from ACT."""

    __tablename__ = "parcels"
    __table_args__ = (
        UniqueConstraint(
            "cadastral_commune_code", "section_code", "numero_principal", "numero_secondaire"
        ),
        Index(
            "ix_parcels_cadastral_ref", "cadastral_commune_code", "section_code", "numero_principal"
        ),
        Index("ix_parcels_admin_commune", "admin_commune_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Raw ID_PARCELLE, format CCCSPPPPPNNNNNN — the natural external identifier
    # (used as the {cadastral_id} path param in the M4 report API).
    cadastral_id: Mapped[str] = mapped_column(String(15), unique=True)
    cadastral_commune_code: Mapped[str] = mapped_column(
        ForeignKey("cadastral_communes.code", ondelete="RESTRICT")
    )
    # Widened to 3 chars — see the matching note on CadastralSection.section_code.
    section_code: Mapped[str] = mapped_column(String(3))
    numero_principal: Mapped[int] = mapped_column(Integer)
    numero_secondaire: Mapped[int] = mapped_column(Integer)
    lieudit: Mapped[str | None] = mapped_column(Text, default=None)
    nature_code: Mapped[int | None] = mapped_column(
        ForeignKey("parcel_natures.code", ondelete="SET NULL"), default=None
    )
    # Propagated from cadastral_communes.admin_commune_code at ingest, not a
    # live spatial join — verified against the real crosswalk that every
    # cadastral commune's sections belong to exactly one administrative
    # commune (no split cases), so this is a safe, exact copy, not a guess.
    # Nullable only if the owning cadastral_communes row itself has no
    # resolved admin code (an honest gap, not silently defaulted).
    admin_commune_code: Mapped[str | None] = mapped_column(
        ForeignKey("communes.lau2_code", ondelete="SET NULL"), default=None
    )
    geom: Mapped[WKBElement] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=2169))
    area_geom_m2: Mapped[float] = mapped_column(
        Numeric(asdecimal=False), Computed("ST_Area(geom)", persisted=True)
    )
    # No source found yet for a declared/legal area (see DECISIONS.md) — never fabricated.
    area_declared_m2: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Building(Base):
    """A PCN building footprint. No parcel FK exists in the source — see ParcelBuilding."""

    __tablename__ = "buildings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    occupation_code: Mapped[int | None] = mapped_column(
        ForeignKey("building_natures.code", ondelete="SET NULL"), default=None
    )
    cadastral_commune_code: Mapped[str | None] = mapped_column(
        ForeignKey("cadastral_communes.code", ondelete="SET NULL"), default=None
    )
    geom: Mapped[WKBElement] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=2169))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ParcelBuilding(Base):
    """Persisted many-to-many: a building may overlap more than one parcel.

    Computed once at ingest via ST_Intersects; the M1.3 side panel is then a
    plain indexed lookup, not a live geometric query.
    """

    __tablename__ = "parcel_buildings"

    parcel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), primary_key=True
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("buildings.id", ondelete="CASCADE"), primary_key=True
    )
    overlap_m2: Mapped[float] = mapped_column(Numeric(asdecimal=False))


class Address(Base):
    """A BD-Adresses point, resolved onto its parcel via ST_Contains at ingest."""

    __tablename__ = "addresses"
    __table_args__ = (
        Index("ix_addresses_admin_commune", "admin_commune_code"),
        # M1.2's fuzzy/typo-tolerant search depends on this — without it, the
        # `%` similarity operator falls back to a sequential scan (caught by
        # actually running EXPLAIN ANALYZE, not assumed from the design).
        Index(
            "ix_addresses_street_name_trgm",
            "street_name_normalized",
            postgresql_using="gin",
            postgresql_ops={"street_name_normalized": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # BD-Adresses' own `id_geoportail` — the natural idempotency key.
    source_id_geoportail: Mapped[str] = mapped_column(Text, unique=True)
    caclr_rue_id: Mapped[int | None] = mapped_column(Integer, default=None)
    caclr_bat_id: Mapped[int | None] = mapped_column(Integer, default=None)
    street_name: Mapped[str] = mapped_column(Text)
    # Generated (unaccent + lower), indexed with pg_trgm for fuzzy/typo search (M1.2).
    street_name_normalized: Mapped[str] = mapped_column(
        Text, Computed("unaccent_immutable(lower(street_name))", persisted=True)
    )
    house_number: Mapped[str] = mapped_column(String(10))
    locality: Mapped[str | None] = mapped_column(Text, default=None)
    postal_code: Mapped[str | None] = mapped_column(String(10), default=None)
    admin_commune_code: Mapped[str | None] = mapped_column(
        ForeignKey("communes.lau2_code", ondelete="SET NULL"), default=None
    )
    # Nullable: BD-Adresses itself documents that not all addresses are
    # georeferenced/resolvable — an honest gap, not silently dropped.
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parcels.id", ondelete="SET NULL"), default=None
    )
    geom: Mapped[WKBElement] = mapped_column(Geometry(geometry_type="POINT", srid=2169))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
