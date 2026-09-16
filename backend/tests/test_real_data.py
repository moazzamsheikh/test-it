"""End-to-end tests against real ingested data (the 8 brief-named
deep-ingestion communes).

Read-only by design — these assert facts about the actual PCN/BD-Adresses
corpus loaded by `make ingest`, not fixtures. Requires `make ingest` to have
been run first (parcels, buildings, addresses for the target communes).

The specific cadastral_ids/building_ids below were found by querying the real
ingested data (see DECISIONS.md / WALKTHROUGH.md), not invented — if a fresh
weekly PCN/BD-Adresses refresh changes these specific rows, that's a real
signal the source data moved, not a flaky test to silence.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cadastre import Address, Commune, Parcel, ParcelBuilding

# A real Wiltz parcel with zero linked addresses — the M1.3 "zero addresses" edge case.
WILTZ_ZERO_ADDRESS_PARCEL = "127B00746005379"

# A real Luxembourg City parcel with many linked addresses — the M1.3 "fifteen
# addresses" edge case (this one has 37, comfortably past the bar).
LUX_MANY_ADDRESS_PARCEL = "075A00297001263"
MIN_EXPECTED_ADDRESS_COUNT = 15

# Buildings get a fresh random UUID every `make ingest-parcels` run (see
# ingestion/ingest_parcels_buildings.py), unlike cadastral_id above (a real,
# stable natural key from the source data) — a hardcoded building_id here
# went stale the moment the pipeline was re-run for more communes (caught
# live, not anticipated). The M1.3 "building spanning two parcels" edge
# case is instead found fresh each run, by its real defining property.


def test_wiltz_zero_address_parcel_exists(db_session: Session) -> None:
    parcel = db_session.execute(
        select(Parcel).where(Parcel.cadastral_id == WILTZ_ZERO_ADDRESS_PARCEL)
    ).scalar_one()
    assert parcel.cadastral_commune_code == "127"  # Wiltz's own cadastral code
    n_addresses = db_session.execute(
        select(func.count(Address.id)).where(Address.parcel_id == parcel.id)
    ).scalar_one()
    assert n_addresses == 0


def test_luxembourg_parcel_with_many_addresses(db_session: Session) -> None:
    parcel = db_session.execute(
        select(Parcel).where(Parcel.cadastral_id == LUX_MANY_ADDRESS_PARCEL)
    ).scalar_one()
    n_addresses = db_session.execute(
        select(func.count(Address.id)).where(Address.parcel_id == parcel.id)
    ).scalar_one()
    assert n_addresses >= MIN_EXPECTED_ADDRESS_COUNT


def test_building_spans_multiple_parcels_with_real_overlap(db_session: Session) -> None:
    multi_parcel_building_id = db_session.execute(
        select(ParcelBuilding.building_id)
        .group_by(ParcelBuilding.building_id)
        .having(func.count() >= 2)
        .limit(1)
    ).scalar_one_or_none()
    assert multi_parcel_building_id is not None, "no real multi-parcel building found"

    links = (
        db_session.execute(
            select(ParcelBuilding).where(ParcelBuilding.building_id == multi_parcel_building_id)
        )
        .scalars()
        .all()
    )
    assert len(links) >= 2
    # Every linked overlap must be a real area, not the boundary-touch noise
    # (down to 1e-6 m²) that a plain `ST_Area(...) > 0` filter let through
    # before the fix logged in DECISIONS.md.
    assert all(link.overlap_m2 > 1.0 for link in links)


def test_every_ingested_parcel_has_positive_area(db_session: Session) -> None:
    """Sanity check across the whole ingested set, not just one row — no
    parcel should have zero or negative computed area."""
    min_area = db_session.execute(select(func.min(Parcel.area_geom_m2))).scalar_one()
    assert min_area is not None
    assert min_area > 0


def test_every_ingested_parcel_admin_commune_is_a_target_commune(db_session: Session) -> None:
    """Every parcel's admin_commune_code must resolve to one of the 8
    brief-named deep-ingestion communes — proves the cadastral_communes ->
    communes propagation held across the whole ingested set, not just the
    rows we spot-checked by hand."""
    target_names = {
        "Wiltz",
        "Luxembourg",
        "Esch-sur-Alzette",
        "Differdange",
        "Dudelange",
        "Schengen",
        "Junglinster",
        "Sanem",
    }
    rows = db_session.execute(
        select(Parcel.admin_commune_code, Commune.name)
        .join(Commune, Commune.lau2_code == Parcel.admin_commune_code)
        .distinct()
    ).all()
    assert rows, "no parcels found — did `make ingest` run?"
    for _, name in rows:
        assert name in target_names


def test_address_geometry_actually_falls_within_its_resolved_parcel(db_session: Session) -> None:
    """Not just that parcel_id is non-null — that the resolved parcel's real
    geometry actually covers the address point (ST_Covers, inclusive of the
    boundary — see DECISIONS.md on why not ST_Contains)."""
    address_id = db_session.execute(
        select(Address.id).where(Address.parcel_id.is_not(None)).limit(1)
    ).scalar_one()
    covers = db_session.execute(
        select(func.ST_Covers(Parcel.geom, Address.geom))
        .select_from(Address)
        .join(Parcel, Parcel.id == Address.parcel_id)
        .where(Address.id == address_id)
    ).scalar_one()
    assert covers is True


def test_parcel_geometry_srid_is_luref_2169(db_session: Session) -> None:
    parcel = db_session.execute(select(Parcel).limit(1)).scalar_one()
    srid = db_session.execute(
        select(func.ST_SRID(Parcel.geom)).where(Parcel.id == parcel.id)
    ).scalar_one()
    assert srid == 2169
