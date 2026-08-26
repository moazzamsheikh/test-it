"""Controlled vocabularies stored as native PostgreSQL enum types.

Kept deliberately small and explicit — these drive metadata filtering in
retrieval (M3) and the legal_status guard against citing repealed text.
"""

from __future__ import annotations

import enum


class LegalStatus(enum.StrEnum):
    in_force = "in_force"
    repealed = "repealed"
    draft = "draft"
    superseded = "superseded"
    unknown = "unknown"  # freshly fetched, status not yet determined


class Language(enum.StrEnum):
    fr = "fr"
    de = "de"
    lb = "lb"
    en = "en"
    unknown = "unknown"


class DocumentType(enum.StrEnum):
    # National legislation (Legilux)
    loi = "loi"
    reglement_grand_ducal = "reglement_grand_ducal"
    # Communal urban planning
    pag_written = "pag_written"
    pag_graphic = "pag_graphic"
    pap_qe = "pap_qe"
    pap_nq = "pap_nq"
    building_bylaw = "building_bylaw"  # règlement sur les bâtisses
    other_bylaw = "other_bylaw"
    # National spatial planning
    sectoral_plan = "sectoral_plan"
    # Geodata / overlays
    geospatial_layer = "geospatial_layer"
    # Procedures
    procedure_guide = "procedure_guide"
    form = "form"
    other = "other"


class AccessMethod(enum.StrEnum):
    api = "api"
    bulk = "bulk"
    scrape = "scrape"
    wfs = "wfs"
    wms = "wms"
    wmts = "wmts"
    sparql = "sparql"


class SourceStatus(enum.StrEnum):
    never_run = "never_run"
    ok = "ok"
    failed = "failed"
    stale = "stale"
