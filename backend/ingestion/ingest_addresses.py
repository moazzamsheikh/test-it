"""Ingest BD-Adresses for the target communes (M1.2).

Run with: make ingest-addresses
"""

from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Any, cast

import structlog
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.cadastre import Address, Commune
from ingestion.config import BD_ADRESSES_CSV_URL, TARGET_ADMIN_COMMUNES
from ingestion.download_cache import download_cached

logger = structlog.get_logger(__name__)

# See ingest_parcels_buildings.py: Postgres caps bound parameters at 65535 per
# statement, and Luxembourg City has enough addresses to hit that in one go.
_BATCH_SIZE = 2000


def _batched(values: list[dict[str, Any]], size: int = _BATCH_SIZE) -> list[list[dict[str, Any]]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def resolve_target_lau2_codes(session: Session) -> set[str]:
    rows = (
        session.execute(select(Commune.lau2_code).where(Commune.name.in_(TARGET_ADMIN_COMMUNES)))
        .scalars()
        .all()
    )
    if not rows:
        raise RuntimeError(
            f"No communes resolved for {TARGET_ADMIN_COMMUNES} — did you run `make seed-reference`?"
        )
    return set(rows)


def ingest_addresses(session: Session, csv_path: Path, target_lau2: set[str]) -> int:
    values = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row["lau2"].strip() not in target_lau2:
                continue
            values.append(
                {
                    "id": uuid.uuid4(),
                    "source_id_geoportail": row["id_geoportail"].strip(),
                    "caclr_rue_id": (
                        int(row["id_caclr_rue"]) if row["id_caclr_rue"].strip() else None
                    ),
                    "caclr_bat_id": (
                        int(row["id_caclr_bat"]) if row["id_caclr_bat"].strip() else None
                    ),
                    "street_name": row["rue"].strip(),
                    "house_number": row["numero"].strip(),
                    "locality": row["localite"].strip() or None,
                    "postal_code": row["code_postal"].strip() or None,
                    "admin_commune_code": row["lau2"].strip(),
                    "geom": from_shape(
                        Point(float(row["coord_est_luref"]), float(row["coord_nord_luref"])),
                        srid=2169,
                    ),
                }
            )
    for batch in _batched(values):
        stmt = insert(Address).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Address.source_id_geoportail],
            set_={
                "caclr_rue_id": stmt.excluded.caclr_rue_id,
                "caclr_bat_id": stmt.excluded.caclr_bat_id,
                "street_name": stmt.excluded.street_name,
                "house_number": stmt.excluded.house_number,
                "locality": stmt.excluded.locality,
                "postal_code": stmt.excluded.postal_code,
                "admin_commune_code": stmt.excluded.admin_commune_code,
                "geom": stmt.excluded.geom,
            },
        )
        session.execute(stmt)
    return len(values)


def link_addresses_to_parcels(session: Session, target_lau2: set[str]) -> int:
    """Resolve addresses.parcel_id via ST_Covers (inclusive of the boundary —
    an address sitting exactly on a parcel edge should still resolve, unlike
    ST_Contains, which excludes it). Known limitation, not engineered around:
    if a point sits exactly on a shared edge between two parcels, Postgres
    picks one of the matches arbitrarily (see WALKTHROUGH.md)."""
    result = session.execute(
        text("""
            UPDATE addresses a
            SET parcel_id = p.id
            FROM parcels p
            WHERE a.admin_commune_code = ANY(:codes)
              AND ST_Covers(p.geom, a.geom)
              AND a.parcel_id IS DISTINCT FROM p.id
            """),
        {"codes": list(target_lau2)},
    )
    return cast(CursorResult[Any], result).rowcount


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        target_lau2 = resolve_target_lau2_codes(session)
        logger.info("ingest.addresses.target_lau2", codes=sorted(target_lau2))

        csv_path = download_cached(BD_ADRESSES_CSV_URL, "addresses.csv")
        n_addresses = ingest_addresses(session, csv_path, target_lau2)
        session.commit()

        n_linked = link_addresses_to_parcels(session, target_lau2)
        session.commit()

    logger.info("ingest.addresses.complete", addresses=n_addresses, linked_to_parcel=n_linked)


if __name__ == "__main__":
    main()
