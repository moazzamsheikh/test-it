"""M2 PAG/PAP zoning lookups — a real polygon-polygon spatial join against
`pag_zones`/`pap_qe_zones` (ingested by ingestion/ingest_pag_zones.py from
ACT's real per-commune PAG open data — see PAG_PAP_SPEC.md/DECISIONS.md).

Unlike M1.4's overlay point-sampling (the only option there, since no WFS
exists on that WMS), this is an exact polygon intersection against real
ingested geometry — every intersecting zone is returned, not a sampled
approximation. Results are reported exactly as the real data says, even
when surprising (see DECISIONS.md on the real "FOR" zone covering a built
Ville-Haute address) — never adjusted to look more plausible.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.models.pag import PagZone, PapNqZone, PapQeZone
from app.schemas.pag import PagZoneMatch, PagZoningInfo, PapNqZoneMatch, PapQeZoneMatch
from app.schemas.parcel import OverlayConstraint
from app.services.documents import get_document_reference

# ACT's own PAG legend groups these four ZONAGE categories under the
# heading "Zone verte" (agricole/forestière/parc public/verdure) — verified
# live against the real GetLegendGraphic image for layer 698 (see
# DECISIONS.md). Not a separate WMS layer; a real sub-classification of the
# PAG zoning we already ingest via M2.
_ZONE_VERTE_CATEGORIES = frozenset({"AGR", "FOR", "PARC", "VERD"})

# Real per-commune PAG dataset pages (data.public.lu) — the same datasets
# ingested by ingestion/ingest_pag_zones.py, used here as a human-readable
# "read more" source rather than the raw ZIP URL.
_PAG_DATASET_PAGE_URLS = {
    "0304": "https://data.public.lu/en/datasets/pag-ville-de-luxembourg/",
    "0807": "https://data.public.lu/fr/datasets/pag-wiltz/",
}


async def get_pag_zoning(session: AsyncSession, parcel_id: uuid.UUID) -> PagZoningInfo:
    parcel_geom = select(Parcel.geom).where(Parcel.id == parcel_id).scalar_subquery()

    pag_rows = (
        await session.execute(
            select(
                PagZone.category,
                PagZone.genre,
                PagZone.written_document_id,
                func.ST_Area(func.ST_Intersection(PagZone.geom, parcel_geom)).label("overlap_m2"),
            )
            .where(func.ST_Intersects(PagZone.geom, parcel_geom))
            .order_by(func.ST_Area(func.ST_Intersection(PagZone.geom, parcel_geom)).desc())
        )
    ).all()

    pag_zones = [
        PagZoneMatch(
            category=row.category,
            genre=row.genre,
            overlap_m2=float(row.overlap_m2),
            document=await get_document_reference(session, row.written_document_id),
        )
        for row in pag_rows
    ]

    qe_rows = (
        await session.execute(
            select(
                PapQeZone.written_document_id,
                PapQeZone.graphic_document_filename,
                func.ST_Area(func.ST_Intersection(PapQeZone.geom, parcel_geom)).label("overlap_m2"),
            )
            .where(func.ST_Intersects(PapQeZone.geom, parcel_geom))
            .order_by(func.ST_Area(func.ST_Intersection(PapQeZone.geom, parcel_geom)).desc())
        )
    ).all()

    pap_qe_zones = [
        PapQeZoneMatch(
            overlap_m2=float(row.overlap_m2),
            written_document=await get_document_reference(session, row.written_document_id),
            graphic_document_filename=row.graphic_document_filename,
        )
        for row in qe_rows
    ]

    nq_rows = (
        await session.execute(
            select(
                PapNqZone.denomination,
                PapNqZone.genre,
                PapNqZone.cos_min,
                PapNqZone.cos_max,
                PapNqZone.cus_min,
                PapNqZone.cus_max,
                PapNqZone.css_max,
                PapNqZone.dl_min,
                PapNqZone.dl_max,
                PapNqZone.written_document_id,
                PapNqZone.schema_directeur_filename,
                PapNqZone.schema_directeur_graphic_filename,
                func.ST_Area(func.ST_Intersection(PapNqZone.geom, parcel_geom)).label("overlap_m2"),
            )
            .where(func.ST_Intersects(PapNqZone.geom, parcel_geom))
            .order_by(func.ST_Area(func.ST_Intersection(PapNqZone.geom, parcel_geom)).desc())
        )
    ).all()

    pap_nq_zones = [
        PapNqZoneMatch(
            denomination=row.denomination,
            genre=row.genre,
            cos_min=row.cos_min,
            cos_max=row.cos_max,
            cus_min=row.cus_min,
            cus_max=row.cus_max,
            css_max=row.css_max,
            dl_min=row.dl_min,
            dl_max=row.dl_max,
            overlap_m2=float(row.overlap_m2),
            written_document=await get_document_reference(session, row.written_document_id),
            schema_directeur_filename=row.schema_directeur_filename,
            schema_directeur_graphic_filename=row.schema_directeur_graphic_filename,
        )
        for row in nq_rows
    ]

    return PagZoningInfo(pag_zones=pag_zones, pap_qe_zones=pap_qe_zones, pap_nq_zones=pap_nq_zones)


def derive_m14_style_constraints(
    zoning: PagZoningInfo, admin_commune_code: str | None
) -> list[OverlayConstraint]:
    """Two categories from the M1.4 brief's own required overlay list
    ("zone verte"; "PAP NQ / PAP QE perimeters") aren't separate WMS layers
    at all — confirmed no such layer exists anywhere in the 1437-layer
    geoportail tree (see SOURCES.md). Both are derivable from the real M2
    PAG data already fetched for this parcel — and more precisely than the
    WMS point-sampling used for the other 18 M1.4 layers (exact polygon
    intersection against every real ingested zone, not a handful of sample
    points) — see DECISIONS.md. Takes an already-computed `PagZoningInfo`
    rather than querying again, since `get_pag_zoning` has already done the
    real work this reuses.
    """
    source_url = _PAG_DATASET_PAGE_URLS.get(admin_commune_code or "", "https://data.public.lu/")

    zone_verte_matches = [z for z in zoning.pag_zones if z.category in _ZONE_VERTE_CATEGORIES]
    zone_verte = OverlayConstraint(
        layer_code="zone_verte",
        label="Zone verte (agricole/forestière/parc/verdure)",
        category="urbanisme",
        intersects=len(zone_verte_matches) > 0,
        overlap_m2=(sum(z.overlap_m2 for z in zone_verte_matches) if zone_verte_matches else None),
        detail=(
            {"categories": [z.category for z in zone_verte_matches]} if zone_verte_matches else None
        ),
        source_url=source_url,
    )

    pap_qe = OverlayConstraint(
        layer_code="pap_qe_perimeter",
        label="PAP Quartier Existant perimeter",
        category="urbanisme",
        intersects=len(zoning.pap_qe_zones) > 0,
        overlap_m2=(
            sum(z.overlap_m2 for z in zoning.pap_qe_zones) if zoning.pap_qe_zones else None
        ),
        detail=None,
        source_url=source_url,
    )

    pap_nq_denominations = [z.denomination for z in zoning.pap_nq_zones if z.denomination]
    pap_nq = OverlayConstraint(
        layer_code="pap_nq_perimeter",
        label="PAP Nouveau Quartier perimeter",
        category="urbanisme",
        intersects=len(zoning.pap_nq_zones) > 0,
        overlap_m2=(
            sum(z.overlap_m2 for z in zoning.pap_nq_zones) if zoning.pap_nq_zones else None
        ),
        detail={"denominations": pap_nq_denominations} if pap_nq_denominations else None,
        source_url=source_url,
    )

    return [zone_verte, pap_qe, pap_nq]
