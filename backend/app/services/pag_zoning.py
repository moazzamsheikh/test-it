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
from app.models.pag import PagZone, PapQeZone
from app.models.provenance import Chunk, Document
from app.schemas.pag import DocumentReference, PagZoneMatch, PagZoningInfo, PapQeZoneMatch


async def _document_reference(
    session: AsyncSession, document_id: uuid.UUID | None
) -> DocumentReference | None:
    if document_id is None:
        return None
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        return None
    chunk = (
        await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal).limit(1)
        )
    ).scalar_one_or_none()
    return DocumentReference(
        title=document.title or "",
        source_url=document.source_url,
        article_ref=chunk.article_ref if chunk else None,
        text=chunk.text if chunk else None,
    )


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
            document=await _document_reference(session, row.written_document_id),
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
            written_document=await _document_reference(session, row.written_document_id),
            graphic_document_filename=row.graphic_document_filename,
        )
        for row in qe_rows
    ]

    return PagZoningInfo(pag_zones=pag_zones, pap_qe_zones=pap_qe_zones)
