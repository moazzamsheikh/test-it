"""Parcel identification and detail lookups (M1.3)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import (
    Address,
    Building,
    BuildingNature,
    CadastralCommune,
    Commune,
    Parcel,
    ParcelBuilding,
    ParcelNature,
)
from app.models.provenance import Document
from app.overlay_layers import OVERLAY_LAYERS_BY_CODE
from app.schemas.parcel import (
    AddressSummary,
    BuildingSummary,
    OverlayConstraint,
    ParcelDetail,
    ParcelSummary,
)
from app.services.documents import get_document_reference
from app.services.geometry_analysis import compute_frontage_m, compute_neighbours
from app.services.legilux_dynamic import ensure_document_from_eli_link
from app.services.overlays import get_or_compute_overlays
from app.services.pag_zoning import derive_m14_style_constraints, get_pag_zoning


def _parcel_summary_query() -> Select[Any]:
    return (
        select(
            Parcel.cadastral_id,
            Parcel.cadastral_commune_code,
            CadastralCommune.name.label("cadastral_commune_name"),
            Parcel.admin_commune_code,
            Commune.name.label("admin_commune_name"),
            Parcel.section_code,
            Parcel.numero_principal,
            Parcel.numero_secondaire,
            Parcel.area_geom_m2,
        )
        .join(CadastralCommune, CadastralCommune.code == Parcel.cadastral_commune_code)
        .outerjoin(Commune, Commune.lau2_code == Parcel.admin_commune_code)
    )


async def identify_by_point(session: AsyncSession, lon: float, lat: float) -> list[ParcelSummary]:
    """Click-to-identify: (lon, lat) in WGS84, transformed to LUREF server-side
    (source geometry is 2169; browser input is 4326 — see DECISIONS.md).

    Returns a LIST, not a single parcel: 0 results is a real outcome (the
    click missed every parcel, e.g. landed on a road), and >1 is a real
    outcome too (the click landed exactly on a shared boundary — an explicit
    graded M1.3 edge case) — both are surfaced honestly, not silently resolved
    by picking one.
    """
    point = func.ST_Transform(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), 2169)
    stmt = _parcel_summary_query().where(func.ST_Covers(Parcel.geom, point))
    rows = (await session.execute(stmt)).all()
    return [ParcelSummary.model_validate(row, from_attributes=True) for row in rows]


async def find_by_reference(
    session: AsyncSession,
    cadastral_commune_code: str,
    section_code: str,
    numero_principal: int,
    numero_secondaire: int | None = None,
) -> list[ParcelSummary]:
    """Search by the cadastral reference an architect already knows: commune +
    section + parcel number (M1.3). numero_secondaire is optional — an
    architect may know the parcel number but not its subdivision suffix."""
    stmt = _parcel_summary_query().where(
        Parcel.cadastral_commune_code == cadastral_commune_code,
        Parcel.section_code == section_code,
        Parcel.numero_principal == numero_principal,
    )
    if numero_secondaire is not None:
        stmt = stmt.where(Parcel.numero_secondaire == numero_secondaire)
    rows = (await session.execute(stmt)).all()
    return [ParcelSummary.model_validate(row, from_attributes=True) for row in rows]


async def get_parcel_id(session: AsyncSession, cadastral_id: str) -> Any | None:
    """Lightweight lookup for endpoints (like slope) that only need the
    internal id, not the full detail payload."""
    return (
        await session.execute(select(Parcel.id).where(Parcel.cadastral_id == cadastral_id))
    ).scalar_one_or_none()


async def get_parcel_detail(session: AsyncSession, cadastral_id: str) -> ParcelDetail | None:
    stmt = _parcel_summary_query().add_columns(
        Parcel.id,
        Parcel.lieudit,
        Parcel.nature_code,
        ParcelNature.label.label("nature_label"),
        Parcel.area_declared_m2,
        func.ST_AsGeoJSON(func.ST_Transform(Parcel.geom, 4326)).label("geometry_wgs84_geojson"),
    )
    stmt = stmt.outerjoin(ParcelNature, ParcelNature.code == Parcel.nature_code).where(
        Parcel.cadastral_id == cadastral_id
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None

    addresses = (
        await session.execute(
            select(Address.id, Address.street_name, Address.house_number, Address.locality).where(
                Address.parcel_id == row.id
            )
        )
    ).all()

    buildings = (
        await session.execute(
            select(
                Building.id,
                Building.occupation_code,
                BuildingNature.label.label("occupation_label"),
                ParcelBuilding.overlap_m2,
            )
            .join(ParcelBuilding, ParcelBuilding.building_id == Building.id)
            .outerjoin(BuildingNature, BuildingNature.code == Building.occupation_code)
            .where(ParcelBuilding.parcel_id == row.id)
        )
    ).all()

    overlay_results = await get_or_compute_overlays(session, row.id)
    frontage_m = await compute_frontage_m(session, row.id)
    neighbours = await compute_neighbours(session, row.id)
    pag_zoning = await get_pag_zoning(session, row.id)

    # Tier-1 overlay layers (see app/overlay_layers.py's `document_url` /
    # `document_url_by_commune`) are governed by one ingested règlement
    # grand-ducal — either a single one nationally, or one per commune for
    # layers governed per-watercourse (flood zones — see DECISIONS.md).
    # Resolved here by source_url, one batched lookup rather than N
    # per-layer queries.
    document_urls: set[str] = set()
    for layer in OVERLAY_LAYERS_BY_CODE.values():
        if layer.document_url is not None:
            document_urls.add(layer.document_url)
        if layer.document_url_by_commune is not None:
            document_urls.update(layer.document_url_by_commune.values())
    document_ids_by_url: dict[str, Any] = {}
    if document_urls:
        doc_rows = (
            await session.execute(
                select(Document.source_url, Document.id).where(
                    Document.source_url.in_(document_urls)
                )
            )
        ).all()
        document_ids_by_url = {r.source_url: r.id for r in doc_rows}

    constraints = []
    for result in overlay_results:
        layer = OVERLAY_LAYERS_BY_CODE[result.layer_code]
        # Dynamic per-feature linking (ZPIN's real `lien_legilux` attribute)
        # takes priority over the static document_url(_by_commune) config —
        # a layer only ever uses one resolution mechanism, never both (see
        # DECISIONS.md on why Natura 2000 still needs the static approach
        # while ZPIN doesn't).
        eli_url = (
            (result.detail or {}).get(layer.document_url_detail_key)
            if layer.document_url_detail_key is not None
            else None
        )
        if isinstance(eli_url, str):
            document_id = await ensure_document_from_eli_link(session, result, eli_url, layer.label)
        else:
            effective_document_url = layer.document_url
            if layer.document_url_by_commune is not None:
                effective_document_url = layer.document_url_by_commune.get(
                    row.admin_commune_code or ""
                )
            document_id = document_ids_by_url.get(effective_document_url or "")
        constraints.append(
            OverlayConstraint(
                layer_code=result.layer_code,
                label=layer.label,
                category=layer.category,
                intersects=result.intersects,
                overlap_m2=result.overlap_m2,
                detail=result.detail,
                source_url=result.source_url,
                document=await get_document_reference(session, document_id),
            )
        )
    # "zone verte" and "PAP NQ/QE perimeters" are named in the M1.4 overlay
    # list but aren't separate WMS layers (see DECISIONS.md) — derived here
    # from the real M2 PAG data already fetched above, at no extra query cost.
    constraints += derive_m14_style_constraints(pag_zoning, row.admin_commune_code)

    return ParcelDetail(
        cadastral_id=row.cadastral_id,
        cadastral_commune_code=row.cadastral_commune_code,
        cadastral_commune_name=row.cadastral_commune_name,
        admin_commune_code=row.admin_commune_code,
        admin_commune_name=row.admin_commune_name,
        section_code=row.section_code,
        numero_principal=row.numero_principal,
        numero_secondaire=row.numero_secondaire,
        area_geom_m2=row.area_geom_m2,
        lieudit=row.lieudit,
        nature_code=row.nature_code,
        nature_label=row.nature_label,
        area_declared_m2=row.area_declared_m2,
        addresses=[AddressSummary.model_validate(a, from_attributes=True) for a in addresses],
        buildings=[BuildingSummary.model_validate(b, from_attributes=True) for b in buildings],
        constraints=constraints,
        frontage_m=frontage_m,
        neighbours=neighbours,
        pag_zoning=pag_zoning,
        geometry_wgs84_geojson=json.loads(row.geometry_wgs84_geojson),
    )
