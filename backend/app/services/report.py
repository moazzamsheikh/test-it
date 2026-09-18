"""M4.1 — assembles the brief's exact parcel report schema from data that
already exists: M1's `get_parcel_detail` (addresses, constraints, PAG/PAP
zoning) plus one extra batched query for the real `Document` metadata
(type/date/legal_status) `DocumentReference` doesn't carry.

Every value here traces to something already ingested and verified
elsewhere in this project — this module reshapes, it does not invent. Where
the brief's schema asks for something this corpus cannot answer (M5's
`required_authorisations`, most of `building_parameters`), the honest
answer is an empty value plus an `open_questions` entry, per the brief's
own non-negotiable rule, not a plausible-looking guess.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provenance import Document, Source
from app.schemas.parcel import ParcelDetail
from app.schemas.report import (
    ApplicableDocument,
    BuildingParameters,
    DataFreshness,
    ParcelReport,
    ReportConstraint,
    ReportParcel,
    ReportZoning,
)
from app.services.pag_zoning import derive_pag_zone_label
from app.services.parcels import get_parcel_detail

# Exact polygon intersection against real M2 PAG data (see
# app/services/pag_zoning.py) — unlike the WMS-sampled layers below, these
# three are never a sampled approximation.
_EXACT_GEOMETRY_LAYER_CODES = frozenset({"zone_verte", "pap_qe_perimeter", "pap_nq_perimeter"})

# One neutral, factual sentence per real overlay layer — what a "yes" here
# generally means for a construction project, not a legal opinion. Falls
# back to a generic per-category sentence for any layer_code not listed
# (keeps this from silently going stale if a new layer is added).
_CONSEQUENCE_BY_LAYER_CODE: dict[str, str] = {
    "pag_zoning": (
        "Parcel falls within a classified PAG zone — the zone's written "
        "regulation governs what can be built."
    ),
    "pap_approuves": (
        "Parcel falls within an individually approved PAP project with its own specific rules."
    ),
    "pos": "A state-level Plan d'Occupation du Sol overrides communal zoning here.",
    "psl": (
        "A binding national housing-development sectoral plan applies, "
        "potentially setting density requirements."
    ),
    "pst": (
        "A reserved transport-infrastructure corridor applies — may restrict "
        "development or require clearance."
    ),
    "pszae": "A national economic-activity-zone sectoral plan applies.",
    "psp": "A binding landscape-protection sectoral plan applies — may restrict development.",
    "zone_verte": (
        "Parcel falls in a 'zone verte' (agricole/forestière/parc/verdure) — "
        "construction is heavily restricted and typically requires ANF authorisation."
    ),
    "pap_qe_perimeter": (
        "Parcel falls within a PAP Quartier Existant perimeter — integration rules "
        "for the existing built context apply, in addition to the base PAG zone."
    ),
    "pap_nq_perimeter": (
        "Parcel falls within a PAP Nouveau Quartier perimeter — a dedicated "
        "urbanisation project defines the applicable coefficients here, not the "
        "base PAG zone alone."
    ),
    "natura2000_habitats": (
        "Parcel intersects a Natura 2000 habitats-directive site — an "
        "environmental impact assessment is typically required before construction."
    ),
    "natura2000_oiseaux": (
        "Parcel intersects a Natura 2000 birds-directive site — an "
        "environmental impact assessment is typically required before construction."
    ),
    "reserves_naturelles": (
        "Parcel falls within a national nature reserve — construction and tree "
        "removal typically require ANF authorisation."
    ),
    "flood_hq20": (
        "Parcel is within the 20-year flood return-period zone — construction "
        "may require flood-mitigation measures."
    ),
    "flood_hq100": (
        "Parcel is within the 100-year flood return-period zone — construction "
        "may require flood-mitigation measures and AGE authorisation."
    ),
    "water_protection": (
        "Parcel falls within a drinking-water catchment protection zone — "
        "activities affecting groundwater are restricted."
    ),
    "heritage_ssmn": (
        "Parcel or building is within a protected heritage perimeter — heritage "
        "authorisation (INPA) is typically required before altering the building "
        "or its surroundings."
    ),
    "archaeological_sites": (
        "Parcel intersects a known archaeological site — excavation/foundation "
        "work may require prior INPA clearance."
    ),
    "noise_airport": (
        "Parcel is within a Findel airport noise-exposure zone — may affect "
        "habitability requirements."
    ),
    "findel_servitude": (
        "Parcel is within a Findel airport aeronautical servitude — height "
        "restrictions apply to any construction."
    ),
    "gas_network": (
        "Parcel is near a high-pressure gas main — Creos clearance is typically "
        "required before excavation or construction nearby."
    ),
}

_CATEGORY_FALLBACK_CONSEQUENCE = {
    "urbanisme": "A communal urban-planning constraint applies to this parcel.",
    "sectoriel": "A binding national sectoral plan applies to this parcel.",
    "environnement": "An environmental protection constraint applies to this parcel.",
    "risques": "A risk-zone constraint applies to this parcel.",
    "eau": "A water-related constraint applies to this parcel.",
    "patrimoine": "A heritage protection constraint applies to this parcel.",
    "nuisances": "A nuisance/exposure constraint applies to this parcel.",
    "servitudes": "A servitude restricting construction applies to this parcel.",
    "reseaux": "A utility-network proximity constraint applies to this parcel.",
}

_APPLICABLE_DOCUMENT_RELEVANCE = {
    "pag_written": "Written regulation for the PAG zone this parcel is classified under.",
    "pag_graphic": "Graphic map of the applicable PAG/PAP zoning for this parcel.",
    "pap_qe": (
        "Written regulation for the PAP Quartier Existant sub-zone applying to this parcel."
    ),
    "pap_nq": (
        "Written regulation for the PAP Nouveau Quartier development applying to this parcel."
    ),
    "building_bylaw": (
        "Commune building bylaw (règlement sur les bâtisses) applicable to "
        "construction on this parcel."
    ),
    "loi": "National legislation relevant to this parcel's constraints.",
    "reglement_grand_ducal": (
        "National règlement grand-ducal governing one of this parcel's constraints."
    ),
    "sectoral_plan": "Binding national sectoral plan applying to this parcel.",
    "other_bylaw": "Other commune bylaw relevant to this parcel.",
    "other": "Document relevant to this parcel's regulatory constraints.",
}


def _summarize_detail(detail: dict[str, object] | None) -> str | None:
    if not detail:
        return None
    return "; ".join(f"{k}={v}" for k, v in detail.items())


def _confidence_for(layer_code: str, applies: bool) -> str:
    if layer_code in _EXACT_GEOMETRY_LAYER_CODES:
        return "high"
    # WMS point-sampling (see app/services/overlays.py): a real hit is exact
    # (GetFeatureInfo returns the actual feature), but a miss could be a
    # thin overlay strip the sample points didn't land on — so "applies"
    # is high-confidence, "does not apply" is not quite certain.
    return "high" if applies else "medium"


async def _fetch_documents(
    session: AsyncSession, document_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Document]:
    if not document_ids:
        return {}
    rows = (
        (await session.execute(select(Document).where(Document.id.in_(document_ids))))
        .scalars()
        .all()
    )
    return {d.id: d for d in rows}


def _collect_document_ids(parcel: ParcelDetail) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for c in parcel.constraints:
        if c.document is not None and c.document.document_id is not None:
            ids.add(c.document.document_id)
    for pag_zone in parcel.pag_zoning.pag_zones:
        if pag_zone.document is not None and pag_zone.document.document_id is not None:
            ids.add(pag_zone.document.document_id)
    for qe_zone in parcel.pag_zoning.pap_qe_zones:
        for ref in (qe_zone.written_document, qe_zone.graphic_document):
            if ref is not None and ref.document_id is not None:
                ids.add(ref.document_id)
    for nq_zone in parcel.pag_zoning.pap_nq_zones:
        for ref in (nq_zone.written_document, nq_zone.schema_directeur_graphic_document):
            if ref is not None and ref.document_id is not None:
                ids.add(ref.document_id)
    return ids


async def build_parcel_report(session: AsyncSession, cadastral_id: str) -> ParcelReport | None:
    parcel = await get_parcel_detail(session, cadastral_id)
    if parcel is None:
        return None

    document_ids = _collect_document_ids(parcel)
    documents_by_id = await _fetch_documents(session, document_ids)

    open_questions: list[str] = []

    # --- zoning ---
    pag_zone = parcel.pag_zoning.pag_zones[0] if parcel.pag_zoning.pag_zones else None
    if len(parcel.pag_zoning.pag_zones) > 1:
        open_questions.append(
            f"Parcel spans {len(parcel.pag_zoning.pag_zones)} distinct PAG zones "
            f"({', '.join(z.category for z in parcel.pag_zoning.pag_zones)}) — "
            "showing the one with the largest overlap; the others also apply."
        )

    pap_type: str | None = None
    pap_reference: str | None = None
    pap_document_url: str | None = None
    if parcel.pag_zoning.pap_qe_zones:
        pap_type = "PAP QE"
        qe = parcel.pag_zoning.pap_qe_zones[0]
        pap_reference = qe.graphic_document_filename
        pap_document_url = (qe.written_document.source_url if qe.written_document else None) or (
            qe.graphic_document.source_url if qe.graphic_document else None
        )
    elif parcel.pag_zoning.pap_nq_zones:
        pap_type = "PAP NQ"
        nq = parcel.pag_zoning.pap_nq_zones[0]
        pap_reference = nq.denomination
        pap_document_url = nq.written_document.source_url if nq.written_document else None

    if parcel.pag_zoning.pap_qe_zones and parcel.pag_zoning.pap_nq_zones:
        open_questions.append(
            "Parcel intersects both a PAP Quartier Existant zone and a PAP Nouveau "
            "Quartier zone — `zoning.pap_type` only reports PAP QE (shown first); "
            "the NQ zone's own COS/CUS/CSS/DL coefficients are still reflected in "
            "building_parameters below."
        )

    sectoral_plans = [
        c.label
        for c in parcel.constraints
        if c.layer_code in {"psl", "pst", "pszae", "psp"} and c.intersects
    ]

    zoning = ReportZoning(
        pag_zone=pag_zone.category if pag_zone else None,
        pag_zone_label=(
            derive_pag_zone_label(pag_zone.category, pag_zone.document) if pag_zone else None
        ),
        pag_document_url=(pag_zone.document.source_url if pag_zone and pag_zone.document else None),
        pap_type=pap_type,
        pap_reference=pap_reference,
        pap_document_url=pap_document_url,
        sectoral_plans=sectoral_plans,
    )

    # --- building parameters ---
    nq_zones = parcel.pag_zoning.pap_nq_zones
    if nq_zones:
        nq = nq_zones[0]
        building_parameters = BuildingParameters(
            max_height_m=None,
            max_storeys=None,
            setback_front_m=None,
            setback_side_m=None,
            setback_rear_m=None,
            max_footprint_ratio=nq.cos_max,
            max_density=nq.dl_max,
            extraction_confidence="medium",
        )
        open_questions.append(
            "Height/storeys/setback values could not be reliably extracted for this "
            "parcel's applicable PAP NQ zone (no GIS attribute or parsed table exists "
            "for them yet) — only max_footprint_ratio/max_density (COS/DL) are real "
            "extracted GIS attributes; treat the rest as a manual input."
        )
    else:
        building_parameters = BuildingParameters(
            max_height_m=None,
            max_storeys=None,
            setback_front_m=None,
            setback_side_m=None,
            setback_rear_m=None,
            max_footprint_ratio=None,
            max_density=None,
            extraction_confidence="not_extracted",
        )
        open_questions.append(
            "No building parameters (height/storeys/setbacks/coefficients) could be "
            "extracted for this parcel — the applicable PAG/PAP QE written regulation "
            "must be read manually. Reliable extraction only exists for parcels in a "
            "PAP Nouveau Quartier zone (real COS/CUS/CSS/DL GIS attributes)."
        )

    # --- constraints ---
    constraints = [
        ReportConstraint(
            type=c.layer_code,
            applies=c.intersects,
            detail=_summarize_detail(c.detail),
            source_url=c.source_url,
            confidence=_confidence_for(c.layer_code, c.intersects),
            consequence=_CONSEQUENCE_BY_LAYER_CODE.get(
                c.layer_code,
                _CATEGORY_FALLBACK_CONSEQUENCE.get(
                    c.category, "A regulatory constraint applies to this parcel."
                ),
            ),
        )
        for c in parcel.constraints
    ]

    # --- applicable documents ---
    applicable_documents = [
        ApplicableDocument(
            title=doc.title or "",
            type=doc.document_type.value,
            url=doc.source_url,
            date=doc.document_date,
            legal_status=doc.legal_status.value,
            relevance=_APPLICABLE_DOCUMENT_RELEVANCE.get(
                doc.document_type.value,
                "Document relevant to this parcel's regulatory constraints.",
            ),
        )
        for doc in documents_by_id.values()
    ]

    # --- required authorisations (M5 not built yet — honest gap, not a guess) ---
    required_authorisations: list[str] = []
    open_questions.append(
        "Required authorisations are not determined — the M5 decision engine "
        "(building-programme-driven authorisation rules) has not been built yet."
    )

    # --- data freshness (real M2.1 Source tracking, not fabricated) ---
    by_document_type: dict[str, datetime | None] = {}
    if document_ids:
        source_rows = (
            await session.execute(
                select(Document.document_type, Source.last_success_at)
                .join(Source, Source.id == Document.source_id)
                .where(Document.id.in_(document_ids))
            )
        ).all()
        for doc_type, last_success_at in source_rows:
            existing = by_document_type.get(doc_type.value)
            if existing is None or (last_success_at is not None and last_success_at > existing):
                by_document_type[doc_type.value] = last_success_at
    timestamps = [t for t in by_document_type.values() if t is not None]
    data_freshness = DataFreshness(
        oldest_source_last_success_at=min(timestamps) if timestamps else None,
        newest_source_last_success_at=max(timestamps) if timestamps else None,
        by_document_type=by_document_type,
    )

    return ParcelReport(
        parcel=ReportParcel(
            id=parcel.cadastral_id,
            commune=parcel.admin_commune_name,
            section=parcel.section_code,
            area_m2=parcel.area_geom_m2,
            area_declared_m2=parcel.area_declared_m2,
            geometry=parcel.geometry_wgs84_geojson,
        ),
        addresses=parcel.addresses,
        zoning=zoning,
        building_parameters=building_parameters,
        constraints=constraints,
        applicable_documents=applicable_documents,
        required_authorisations=required_authorisations,
        open_questions=open_questions,
        generated_at=datetime.now(UTC),
        data_freshness=data_freshness,
    )
