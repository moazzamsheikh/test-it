"""Schema-level correctness tests: constraints and generated columns.

Everything here runs inside `db_session`'s rolled-back transaction (see
conftest.py) — nothing persists past the test. Uses real seeded reference
rows (cadastral_communes, parcel_natures) as FK targets rather than inventing
fixture data, since `make seed-reference` is a prerequisite for the app to
work at all.
"""

from __future__ import annotations

import uuid

import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, Polygon
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cadastre import (
    Address,
    Building,
    CadastralCommune,
    ParcelBuilding,
    ParcelNature,
)
from app.models.cadastre import (
    Parcel as ParcelModel,
)


def _square(x: float, y: float, side: float) -> Polygon:
    return Polygon([(x, y), (x + side, y), (x + side, y + side), (x, y + side), (x, y)])


def _small_building() -> Building:
    return Building(id=uuid.uuid4(), geom=from_shape(_square(77010.0, 75010.0, 10.0), srid=2169))


def _real_cadastral_commune_code(session: Session) -> str:
    code = session.execute(select(CadastralCommune.code).limit(1)).scalar_one_or_none()
    assert code is not None, "no cadastral_communes seeded — run `make seed-reference` first"
    return code


def _real_parcel_nature_code(session: Session) -> int:
    code = session.execute(select(ParcelNature.code).limit(1)).scalar_one_or_none()
    assert code is not None, "no parcel_natures seeded — run `make seed-reference` first"
    return code


def _make_square_parcel(
    session: Session, cadastral_id: str, x: float = 77000.0, y: float = 75000.0, side: float = 100.0
) -> ParcelModel:
    commune_code = _real_cadastral_commune_code(session)
    nature_code = _real_parcel_nature_code(session)
    parcel = ParcelModel(
        id=uuid.uuid4(),
        cadastral_id=cadastral_id,
        cadastral_commune_code=commune_code,
        section_code="Z",
        numero_principal=999999,
        numero_secondaire=999999,
        nature_code=nature_code,
        geom=from_shape(_square(x, y, side), srid=2169),
    )
    session.add(parcel)
    session.flush()
    return parcel


def test_area_geom_computed_from_geometry(db_session: Session) -> None:
    """A 100x100 m square must compute area_geom_m2 == 10000, via PostGIS ST_Area,
    not something we set ourselves — proves the generated column actually runs."""
    parcel = _make_square_parcel(db_session, "TEST0000000001", side=100.0)
    db_session.refresh(parcel)
    assert parcel.area_geom_m2 == pytest.approx(10000.0, rel=1e-6)


def test_parcel_cadastral_id_unique(db_session: Session) -> None:
    _make_square_parcel(db_session, "TEST0000000002")
    # A real SAVEPOINT (not the outer per-test transaction from conftest.py) so
    # the expected failure rolls back only this insert, leaving the fixture's
    # own transaction alone for the rest of the test / its teardown.
    with pytest.raises(IntegrityError), db_session.begin_nested():
        _make_square_parcel(db_session, "TEST0000000002", x=78000.0)


def test_parcel_cadastral_commune_code_fk_enforced(db_session: Session) -> None:
    """A parcel referencing a cadastral commune that doesn't exist must be rejected —
    this is the FK the M1.3 cadastral-reference search depends on."""
    parcel = ParcelModel(
        id=uuid.uuid4(),
        cadastral_id="TEST0000000003",
        cadastral_commune_code="999",  # does not exist
        section_code="Z",
        numero_principal=1,
        numero_secondaire=1,
        geom=from_shape(_square(77000.0, 75000.0, 100.0), srid=2169),
    )
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(parcel)
        db_session.flush()


def test_address_street_name_normalized_unaccents_and_lowercases(db_session: Session) -> None:
    """Proves the unaccent_immutable generated column, not just that it exists —
    this is what makes M1.2's fuzzy/accent-insensitive search possible."""
    address = Address(
        id=uuid.uuid4(),
        source_id_geoportail="test_address_1",
        street_name="Allée Léopold Goebel",
        house_number="12A",
        geom=from_shape(Point(77000.0, 75000.0), srid=2169),
    )
    db_session.add(address)
    db_session.flush()
    db_session.refresh(address)
    assert address.street_name_normalized == "allee leopold goebel"


def test_parcel_buildings_composite_pk_rejects_duplicate(db_session: Session) -> None:
    """A building spanning >1 parcel is a real, graded M1.3 edge case — the join
    table's composite PK must still reject a literal duplicate (parcel, building) pair."""
    parcel = _make_square_parcel(db_session, "TEST0000000004")
    building = _small_building()
    db_session.add(building)
    db_session.flush()

    db_session.add(ParcelBuilding(parcel_id=parcel.id, building_id=building.id, overlap_m2=100.0))
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            ParcelBuilding(parcel_id=parcel.id, building_id=building.id, overlap_m2=100.0)
        )
        db_session.flush()


def test_deleting_building_cascades_to_parcel_buildings(db_session: Session) -> None:
    """Buildings are replaced whole on every ingest run (no natural key — see
    DECISIONS.md); the cascade is what makes that safe without orphaning links."""
    parcel = _make_square_parcel(db_session, "TEST0000000005")
    building = _small_building()
    db_session.add(building)
    db_session.flush()
    db_session.add(ParcelBuilding(parcel_id=parcel.id, building_id=building.id, overlap_m2=100.0))
    db_session.flush()

    db_session.delete(building)
    db_session.flush()

    remaining = (
        db_session.execute(select(ParcelBuilding).where(ParcelBuilding.parcel_id == parcel.id))
        .scalars()
        .all()
    )
    assert remaining == []
