"""Idempotent seed loader for M1 reference tables.

Loads the small, hand-verified CSVs in backend/app/reference_data/ into
`communes`, `cadastral_communes`, `cadastral_sections`, `parcel_natures` and
`building_natures`. Every write is an upsert keyed on the table's natural
primary key (or unique constraint), so re-running never duplicates rows.

This is NOT tracked through the `sources`/`documents` provenance tables — those
are for the regulatory document corpus (M2). This is static ACT/CACLR reference
vocabulary, not a crawled, citable source.

Run with: make seed-reference
"""

from __future__ import annotations

import csv
from pathlib import Path

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.cadastre import (
    BuildingNature,
    CadastralCommune,
    CadastralSection,
    Commune,
    ParcelNature,
)

logger = structlog.get_logger(__name__)

REFERENCE_DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "reference_data"


def _read_csv(name: str) -> list[dict[str, str]]:
    with (REFERENCE_DATA_DIR / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def seed_communes(session: Session) -> int:
    rows = _read_csv("communes.csv")
    values = [
        {
            "lau2_code": row["CODE_LAU2"].strip(),
            "name": row["COMMUNE"].strip(),
            "canton": row["CANTON"].strip() or None,
            "district": row["DISTRICT"].strip() or None,
            "circonscription_electorale": row["CIRCONSCRIPTION_ELECTORALE"].strip() or None,
            "arrondissement_judiciaire": row["ARRONDISSEMENT_JUDICIAIRE"].strip() or None,
            "surface_m2": (
                float(row["SURFACE_GEOMETRIQUE_COMMUNE_[m2]"])
                if row["SURFACE_GEOMETRIQUE_COMMUNE_[m2]"].strip()
                else None
            ),
        }
        for row in rows
    ]
    stmt = insert(Commune).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Commune.lau2_code],
        set_={
            "name": stmt.excluded.name,
            "canton": stmt.excluded.canton,
            "district": stmt.excluded.district,
            "circonscription_electorale": stmt.excluded.circonscription_electorale,
            "arrondissement_judiciaire": stmt.excluded.arrondissement_judiciaire,
            "surface_m2": stmt.excluded.surface_m2,
        },
    )
    session.execute(stmt)
    return len(values)


def seed_parcel_natures(session: Session) -> int:
    rows = _read_csv("parcel_natures.csv")
    values = [
        {"code": int(r["code"]), "label": r["label"], "category": r["category"]} for r in rows
    ]
    stmt = insert(ParcelNature).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ParcelNature.code],
        set_={"label": stmt.excluded.label, "category": stmt.excluded.category},
    )
    session.execute(stmt)
    return len(values)


def seed_building_natures(session: Session) -> int:
    rows = _read_csv("building_natures.csv")
    values = [
        {"code": int(r["code"]), "label": r["label"], "category": r["category"]} for r in rows
    ]
    stmt = insert(BuildingNature).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[BuildingNature.code],
        set_={"label": stmt.excluded.label, "category": stmt.excluded.category},
    )
    session.execute(stmt)
    return len(values)


def seed_cadastral_communes_and_sections(session: Session) -> tuple[int, int]:
    rows = _read_csv("cadastral_communes_sections.csv")

    # Resolve the crosswalk's administrative commune NAME to our LAU2 code.
    # Verified beforehand that every one of the ~100 names matches exactly
    # against `communes` seeded above — logged, not assumed, if that ever stops
    # being true (e.g. after a future merger renames a commune).
    name_to_lau2: dict[str, str] = {
        name: lau2_code
        for name, lau2_code in session.execute(select(Commune.name, Commune.lau2_code))
    }

    cadastral_communes: dict[str, dict[str, str | None]] = {}
    sections: list[dict[str, str | None]] = []
    unresolved_names: set[str] = set()

    for row in rows:
        code = row["code_commune_cadastrale"].strip()
        name = row["nom_commune_cadastrale"].strip()
        admin_name = row["nom_commune_administrative"].strip()
        admin_code = name_to_lau2.get(admin_name)
        if admin_code is None:
            unresolved_names.add(admin_name)
        cadastral_communes[code] = {"code": code, "name": name, "admin_commune_code": admin_code}
        sections.append(
            {
                "cadastral_commune_code": code,
                "section_code": row["code_section"].strip(),
                "name": row["nom_section"].strip() or None,
            }
        )

    if unresolved_names:
        logger.warning(
            "seed.cadastral_communes.unresolved_admin_name", names=sorted(unresolved_names)
        )

    cc_values = list(cadastral_communes.values())
    cc_stmt = insert(CadastralCommune).values(cc_values)
    cc_stmt = cc_stmt.on_conflict_do_update(
        index_elements=[CadastralCommune.code],
        set_={
            "name": cc_stmt.excluded.name,
            "admin_commune_code": cc_stmt.excluded.admin_commune_code,
        },
    )
    session.execute(cc_stmt)

    sec_stmt = insert(CadastralSection).values(sections)
    sec_stmt = sec_stmt.on_conflict_do_update(
        index_elements=[CadastralSection.cadastral_commune_code, CadastralSection.section_code],
        set_={"name": sec_stmt.excluded.name},
    )
    session.execute(sec_stmt)

    return len(cc_values), len(sections)


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        n_communes = seed_communes(session)
        n_parcel_natures = seed_parcel_natures(session)
        n_building_natures = seed_building_natures(session)
        n_cadastral_communes, n_sections = seed_cadastral_communes_and_sections(session)
        session.commit()

    logger.info(
        "seed.reference_data.complete",
        communes=n_communes,
        parcel_natures=n_parcel_natures,
        building_natures=n_building_natures,
        cadastral_communes=n_cadastral_communes,
        cadastral_sections=n_sections,
    )


if __name__ == "__main__":
    main()
