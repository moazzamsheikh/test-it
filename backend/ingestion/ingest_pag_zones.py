"""Ingest real PAG ZONAGE (base zones) and ZONES_QE (PAP "Quartier Existant"
sub-zones) for the target communes, from ACT's real per-commune PAG open
data (see PAG_PAP_SPEC.md for the research trail and DECISIONS.md for the
design decisions this makes).

Run with: make ingest-pag-zones
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from xml.etree import ElementTree as ET

import structlog
from geoalchemy2.shape import from_shape
from shapely.affinity import affine_transform
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.cadastre import Parcel
from app.models.enums import AccessMethod, DocumentType, Language, LegalStatus, SourceStatus
from app.models.pag import PagZone, PapQeZone
from app.models.provenance import Chunk, Document, Source
from ingestion.config import PAG_ZIP_URLS, USER_AGENT
from ingestion.gml_geometry import parse_gml_polygon
from ingestion.pag_document_extraction import extract_pag_docx
from ingestion.remote_zip import open_remote_zip

logger = structlog.get_logger(__name__)

_GML_PAG_NS = "{http://www.interlis.ch/INTERLIS2.3/GML32/PAG}"
_BATCH_SIZE = 2000


def _batched(values: list[dict[str, Any]], size: int = _BATCH_SIZE) -> list[list[dict[str, Any]]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


class _ZonageFeature:
    __slots__ = ("category", "genre", "nom_fichier", "geom")

    def __init__(
        self, category: str | None, genre: str | None, nom_fichier: str | None, geom: MultiPolygon
    ) -> None:
        self.category = category
        self.genre = genre
        self.nom_fichier = nom_fichier
        self.geom = geom


class _QeFeature:
    __slots__ = ("nom_fichier_ec", "nom_fichier_gr", "geom")

    def __init__(
        self, nom_fichier_ec: str | None, nom_fichier_gr: str | None, geom: MultiPolygon
    ) -> None:
        self.nom_fichier_ec = nom_fichier_ec
        self.nom_fichier_gr = nom_fichier_gr
        self.geom = geom


def _parse_zonage(root: ET.Element) -> list[_ZonageFeature]:
    features = []
    for el in root.iter(f"{_GML_PAG_NS}ZONAGE"):
        geometrie = el.find(f"{_GML_PAG_NS}GEOMETRIE")
        if geometrie is None:
            continue
        features.append(
            _ZonageFeature(
                category=el.findtext(f"{_GML_PAG_NS}CATEGORIE"),
                genre=el.findtext(f"{_GML_PAG_NS}GENRE"),
                nom_fichier=el.findtext(f"{_GML_PAG_NS}NOM_FICHIER"),
                geom=parse_gml_polygon(geometrie),
            )
        )
    return features


def _parse_zones_qe(root: ET.Element) -> list[_QeFeature]:
    features = []
    for el in root.iter(f"{_GML_PAG_NS}ZONES_QE"):
        geometrie = el.find(f"{_GML_PAG_NS}GEOMETRIE")
        if geometrie is None:
            continue
        features.append(
            _QeFeature(
                nom_fichier_ec=el.findtext(f"{_GML_PAG_NS}NOM_FICHIER_EC"),
                nom_fichier_gr=el.findtext(f"{_GML_PAG_NS}NOM_FICHIER_GR"),
                geom=parse_gml_polygon(geometrie),
            )
        )
    return features


def _swap_xy(geom: MultiPolygon) -> MultiPolygon:
    return affine_transform(geom, [0, 1, 1, 0, 0, 0])


def _resolve_axis_swap(
    session: Session, admin_commune_code: str, sample_geoms: list[MultiPolygon]
) -> bool:
    """ACT's own per-commune PAG GML exports have been found to disagree on
    axis order — Luxembourg City's is Easting,Northing; Wiltz's turned out
    to be Northing,Easting (verified live: the parsed-as-is ZONAGE polygons
    had 0% overlap with Wiltz's real parcels; swapped, they matched real
    parcels immediately — see DECISIONS.md). Rather than hardcode a
    per-commune exception (fragile, unexplained, and untested against the
    next commune ingested), this checks empirically against that commune's
    own already-ingested real parcels (M1) and uses whichever orientation
    actually overlaps real geometry. Raises if neither does — a genuine
    unresolved discrepancy, not something to silently guess past.
    """
    sample_union = unary_union(sample_geoms)

    as_parsed_hits = session.execute(
        select(func.count())
        .select_from(Parcel)
        .where(
            Parcel.admin_commune_code == admin_commune_code,
            func.ST_Intersects(Parcel.geom, from_shape(sample_union, srid=2169)),
        )
    ).scalar_one()
    if as_parsed_hits > 0:
        return False

    swapped_hits = session.execute(
        select(func.count())
        .select_from(Parcel)
        .where(
            Parcel.admin_commune_code == admin_commune_code,
            func.ST_Intersects(Parcel.geom, from_shape(_swap_xy(sample_union), srid=2169)),
        )
    ).scalar_one()
    if swapped_hits > 0:
        return True

    raise RuntimeError(
        f"Neither axis order for {admin_commune_code}'s PAG geometry overlaps any real "
        "ingested parcel — a genuine unresolved discrepancy, not a known axis-order quirk."
    )


def _get_or_create_source(session: Session, *, name: str, zip_url: str) -> uuid.UUID:
    stmt = (
        insert(Source)
        .values(
            name=name,
            description="ACT's real per-commune PAG open-data bundle (GML + DOCX + PDF).",
            source_url=zip_url,
            access_method=AccessMethod.bulk,
            publisher="Administration du cadastre et de la topographie (ACT)",
            last_fetch_at=func.now(),
            last_success_at=func.now(),
            last_status=SourceStatus.ok,
        )
        .on_conflict_do_update(
            index_elements=[Source.name],
            set_={
                "last_fetch_at": func.now(),
                "last_success_at": func.now(),
                "last_status": SourceStatus.ok,
            },
        )
        .returning(Source.id)
    )
    return session.execute(stmt).scalar_one()


def _get_or_create_written_document(
    session: Session, *, source_id: uuid.UUID, zip_url: str, entry_name: str, data: bytes
) -> uuid.UUID:
    source_url = f"{zip_url}#{entry_name}"
    sha256 = hashlib.sha256(data).hexdigest()
    existing = session.execute(
        select(Document).where(Document.source_url == source_url, Document.sha256 == sha256)
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    title, text, article_ref = extract_pag_docx(data)
    document = Document(
        source_id=source_id,
        source_url=source_url,
        title=title,
        publisher="Administration du cadastre et de la topographie (ACT)",
        sha256=sha256,
        language=Language.fr,
        legal_status=LegalStatus.unknown,  # a zoning regulation, not itself an act of law
        document_type=DocumentType.pag_written,
    )
    session.add(document)
    session.flush()
    session.add(
        Chunk(
            document_id=document.id,
            ordinal=0,
            heading=title,
            article_ref=article_ref,
            text=text,
            document_type=DocumentType.pag_written,
            language=Language.fr,
            legal_status=LegalStatus.unknown,
        )
    )
    return document.id


def ingest_commune(
    session: Session, admin_commune_code: str, commune_name: str, zip_url: str
) -> dict[str, int]:
    zf = open_remote_zip(zip_url, USER_AGENT)
    gml_names = [n for n in zf.namelist() if n.endswith(".gml")]
    if len(gml_names) != 1:
        raise RuntimeError(f"expected exactly one .gml entry, found {gml_names}")
    gml_bytes = zf.read(gml_names[0])
    root = ET.fromstring(gml_bytes)

    zonage_features = _parse_zonage(root)
    qe_features = _parse_zones_qe(root)
    logger.info(
        "ingest.pag_zones.parsed",
        commune=commune_name,
        zonage=len(zonage_features),
        zones_qe=len(qe_features),
    )

    sample_geoms = [f.geom for f in zonage_features[:20] if f.geom is not None]
    needs_swap = _resolve_axis_swap(session, admin_commune_code, sample_geoms)
    logger.info("ingest.pag_zones.axis_swap", commune=commune_name, needs_swap=needs_swap)
    if needs_swap:
        for zonage_feature in zonage_features:
            zonage_feature.geom = _swap_xy(zonage_feature.geom)
        for qe_feature in qe_features:
            qe_feature.geom = _swap_xy(qe_feature.geom)

    source_id = _get_or_create_source(session, name=f"PAG {commune_name}", zip_url=zip_url)

    written_filenames = {f.nom_fichier for f in zonage_features if f.nom_fichier}
    written_filenames |= {f.nom_fichier_ec for f in qe_features if f.nom_fichier_ec}

    filename_to_document_id: dict[str, uuid.UUID] = {}
    missing_documents = []
    for filename in sorted(written_filenames):
        entry_name = f"{filename}.docx"
        if entry_name not in zf.namelist():
            missing_documents.append(entry_name)
            continue
        data = zf.read(entry_name)
        filename_to_document_id[filename] = _get_or_create_written_document(
            session, source_id=source_id, zip_url=zip_url, entry_name=entry_name, data=data
        )
    if missing_documents:
        logger.warning(
            "ingest.pag_zones.missing_written_documents",
            commune=commune_name,
            missing=missing_documents,
        )
    session.commit()  # documents need real ids before pag_zones/pap_qe_zones reference them

    session.execute(delete(PagZone).where(PagZone.admin_commune_code == admin_commune_code))
    session.execute(delete(PapQeZone).where(PapQeZone.admin_commune_code == admin_commune_code))

    pag_values = [
        {
            "id": uuid.uuid4(),
            "admin_commune_code": admin_commune_code,
            "category": f.category,
            "genre": f.genre,
            "written_document_id": filename_to_document_id.get(f.nom_fichier or ""),
            "geom": from_shape(f.geom, srid=2169),
            "source_url": zip_url,
        }
        for f in zonage_features
        if f.category is not None
    ]
    for batch in _batched(pag_values):
        session.execute(insert(PagZone).values(batch))

    qe_values = [
        {
            "id": uuid.uuid4(),
            "admin_commune_code": admin_commune_code,
            "written_document_id": filename_to_document_id.get(f.nom_fichier_ec or ""),
            "graphic_document_filename": f.nom_fichier_gr,
            "geom": from_shape(f.geom, srid=2169),
            "source_url": zip_url,
        }
        for f in qe_features
    ]
    for batch in _batched(qe_values):
        session.execute(insert(PapQeZone).values(batch))

    return {
        "zonage": len(pag_values),
        "zones_qe": len(qe_values),
        "documents_ingested": len(filename_to_document_id),
    }


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        commune_names = {"0304": "Luxembourg", "0807": "Wiltz"}
        for admin_commune_code, zip_url in PAG_ZIP_URLS.items():
            result = ingest_commune(
                session, admin_commune_code, commune_names[admin_commune_code], zip_url
            )
            session.commit()
            logger.info(
                "ingest.pag_zones.commune_complete",
                commune=commune_names[admin_commune_code],
                **result,
            )
    logger.info("ingest.pag_zones.complete")


if __name__ == "__main__":
    main()
