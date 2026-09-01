"""Ingest PCN parcels and buildings for the target communes (M1.3).

Run with: make ingest-parcels
"""

from __future__ import annotations

import uuid
import zipfile
from pathlib import Path
from typing import Any, cast

import structlog
from geoalchemy2.shape import from_shape
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.cadastre import Building, CadastralCommune, Commune, Parcel
from ingestion.config import CACHE_DIR, PCN_SHAPE_ZIP_URL, TARGET_ADMIN_COMMUNES
from ingestion.download_cache import download_cached
from ingestion.shapefile_reader import as_multipolygon, iter_filtered

logger = structlog.get_logger(__name__)

EXTRACT_DIR = CACHE_DIR / "pcn-shape"

# Postgres caps bound parameters at 65535 per statement. Luxembourg City alone
# has enough parcels that one INSERT ... VALUES (...) for all of them at once
# blows past that (caught by actually running this, not anticipated) — batch
# in chunks small enough to stay well under the limit for any of our tables.
_BATCH_SIZE = 2000


def _batched(values: list[dict[str, Any]], size: int = _BATCH_SIZE) -> list[list[dict[str, Any]]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def _extract_layer(zip_path: Path, layer: str) -> Path:
    """Extract one layer's .shp/.dbf/.shx/.cpg/.prj from the PCN zip, once."""
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    shp_path = EXTRACT_DIR / f"{layer}.shp"
    if shp_path.exists():
        return shp_path
    with zipfile.ZipFile(zip_path) as z:
        for ext in ("shp", "dbf", "shx", "cpg", "prj"):
            name = f"{layer}.{ext}"
            if name in z.namelist():
                z.extract(name, EXTRACT_DIR)
    return shp_path


def resolve_target_cadastral_codes(session: Session) -> dict[str, str | None]:
    """Return {cadastral_commune_code: admin_commune_code} for TARGET_ADMIN_COMMUNES."""
    result = session.execute(
        select(CadastralCommune.code, CadastralCommune.admin_commune_code)
        .join(Commune, Commune.lau2_code == CadastralCommune.admin_commune_code)
        .where(Commune.name.in_(TARGET_ADMIN_COMMUNES))
    )
    code_to_admin = {code: admin_code for code, admin_code in result}
    if not code_to_admin:
        raise RuntimeError(
            f"No cadastral communes resolved for {TARGET_ADMIN_COMMUNES} — "
            "did you run `make seed-reference`?"
        )
    return code_to_admin


def ingest_parcels(session: Session, shp_path: Path, code_to_admin: dict[str, str | None]) -> int:
    def matches(attrs: dict[str, object]) -> bool:
        code_commu = attrs["CODE_COMMU"]
        assert isinstance(code_commu, int)
        return f"{code_commu:03d}" in code_to_admin

    values = []
    for attrs, geom in iter_filtered(shp_path, matches):
        code = f"{int(attrs['CODE_COMMU']):03d}"
        lieudit = attrs["LIEUDIT"]
        nature_code = attrs["CODE_NATUR"]
        values.append(
            {
                "id": uuid.uuid4(),
                "cadastral_id": attrs["ID_PARCELL"],
                "cadastral_commune_code": code,
                "section_code": str(attrs["CODE_SECTI"]).strip(),
                "numero_principal": int(attrs["NUMERO_PRI"]),
                "numero_secondaire": int(attrs["NUMERO_SEC"]),
                "lieudit": str(lieudit).strip() or None if lieudit is not None else None,
                "nature_code": int(nature_code) if nature_code is not None else None,
                "admin_commune_code": code_to_admin[code],
                "geom": from_shape(as_multipolygon(geom), srid=2169),
            }
        )

    for batch in _batched(values):
        stmt = insert(Parcel).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Parcel.cadastral_id],
            set_={
                "section_code": stmt.excluded.section_code,
                "numero_principal": stmt.excluded.numero_principal,
                "numero_secondaire": stmt.excluded.numero_secondaire,
                "lieudit": stmt.excluded.lieudit,
                "nature_code": stmt.excluded.nature_code,
                "admin_commune_code": stmt.excluded.admin_commune_code,
                "geom": stmt.excluded.geom,
            },
        )
        session.execute(stmt)
    return len(values)


def ingest_buildings(session: Session, shp_path: Path, cadastral_codes: set[str]) -> int:
    # BATIMENTS carries no natural key at all (see DECISIONS.md) — full replace
    # scoped to our target communes is the honest idempotency strategy here.
    session.execute(delete(Building).where(Building.cadastral_commune_code.in_(cadastral_codes)))

    def matches(attrs: dict[str, object]) -> bool:
        return str(attrs["CODE_COMMU"]).strip() in cadastral_codes

    values = []
    for attrs, geom in iter_filtered(shp_path, matches):
        occupation_code = attrs["CODE_OCCUP"]
        values.append(
            {
                "id": uuid.uuid4(),
                "occupation_code": (int(occupation_code) if occupation_code is not None else None),
                "cadastral_commune_code": str(attrs["CODE_COMMU"]).strip(),
                "geom": from_shape(as_multipolygon(geom), srid=2169),
            }
        )
    for batch in _batched(values):
        session.execute(insert(Building).values(batch))
    return len(values)


# ST_Intersects is true even for a shared-boundary touch with ~zero area —
# verified on real data: a building "touching" 9 parcels turned out to have
# meaningful overlap (142-420 m²) with only 3 of them, the other 6 being
# floating-point slivers as small as 0.0000012 m². A plain `> 0` threshold
# does not filter these out; require a small but real minimum area instead.
_MIN_MEANINGFUL_OVERLAP_M2 = 1.0


def link_parcel_buildings(session: Session, cadastral_codes: set[str]) -> int:
    """Populate parcel_buildings via ST_Intersects — a building can span >1 parcel."""
    result = session.execute(
        text("""
            INSERT INTO parcel_buildings (parcel_id, building_id, overlap_m2)
            SELECT p.id, b.id, ST_Area(ST_Intersection(p.geom, b.geom))
            FROM buildings b
            JOIN parcels p ON ST_Intersects(b.geom, p.geom)
            WHERE b.cadastral_commune_code = ANY(:codes)
              AND ST_Area(ST_Intersection(p.geom, b.geom)) > :min_overlap
            ON CONFLICT (parcel_id, building_id) DO UPDATE SET overlap_m2 = EXCLUDED.overlap_m2
            """),
        {"codes": list(cadastral_codes), "min_overlap": _MIN_MEANINGFUL_OVERLAP_M2},
    )
    return cast(CursorResult[Any], result).rowcount


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        code_to_admin = resolve_target_cadastral_codes(session)
        cadastral_codes = set(code_to_admin)
        logger.info("ingest.parcels_buildings.target_codes", codes=sorted(cadastral_codes))

        zip_path = download_cached(PCN_SHAPE_ZIP_URL, "pcn-shape.zip")
        parcelles_shp = _extract_layer(zip_path, "PARCELLES")
        batiments_shp = _extract_layer(zip_path, "BATIMENTS")

        n_parcels = ingest_parcels(session, parcelles_shp, code_to_admin)
        n_buildings = ingest_buildings(session, batiments_shp, cadastral_codes)
        session.commit()  # buildings need real ids before the ST_Intersects pass

        n_links = link_parcel_buildings(session, cadastral_codes)
        session.commit()

    logger.info(
        "ingest.parcels_buildings.complete",
        parcels=n_parcels,
        buildings=n_buildings,
        parcel_building_links=n_links,
    )


if __name__ == "__main__":
    main()
