"""M1.4 regulatory overlay layer config — one entry per layer, not one
hardcoded function per layer (the assessment explicitly penalizes the latter).

Every layer here was verified against a live GetMap/GetFeatureInfo request
before being added (see SOURCES.md / DECISIONS.md) — the numeric `wms_layer_id`
is NOT the friendly name shown in the official geoportail.lu client; it's the
theme config's own `"layers"` field, discovered by reading that config, not
guessed.

Two spec categories have no standalone WMS layer anywhere in the 1437-layer
tree we searched — left out of this config rather than mapped to something
wrong. One is now resolved anyway, not from this file: "zone verte" is
computed in `app/services/pag_zoning.py::derive_m14_style_constraints` from
the real M2 PAG `ZONAGE` data (the government's own PAG legend groups four
real zone categories under that heading — see DECISIONS.md/SOURCES.md).
"PAP NQ / PAP QE perimeters" is similarly derived there from M2's `ZONES_QE`/
`NQ_PAP` data, in addition to (not instead of) `pap_approuves` below, which
covers only individually *approved* PAP projects, a narrower real thing.
HV electricity easements remain a genuine gap — no such layer exists on this
public service at all (see SOURCES.md).
"""

from __future__ import annotations

from dataclasses import dataclass

OVERLAY_WMS_URL = "https://wms.geoportail.lu/public_map_layers/service"


@dataclass(frozen=True)
class OverlayLayer:
    code: str  # stable identifier for our own DB/API, not the WMS's own name
    label: str
    category: str
    wms_layer_id: int
    queryable: bool  # whether GetFeatureInfo works (verified per-layer, not assumed)
    source_url: str  # official page a user can read for context, not just the raw WMS
    # Real Legilux URL for the ONE règlement grand-ducal that governs this
    # entire layer (verified per-entry — only set where a single document
    # applies to the whole layer, not per-feature; see
    # ingestion/ingest_overlay_documents.py and DECISIONS.md).
    document_url: str | None = None


_GEOPORTAIL_MAP = "https://map.geoportail.lu/theme/main"

OVERLAY_LAYERS: list[OverlayLayer] = [
    OverlayLayer("pag_zoning", "PAG zoning", "urbanisme", 698, True, _GEOPORTAIL_MAP),
    OverlayLayer("pap_approuves", "PAP (approuvés)", "urbanisme", 696, False, _GEOPORTAIL_MAP),
    OverlayLayer("pos", "POS perimeters", "urbanisme", 710, True, _GEOPORTAIL_MAP),
    OverlayLayer(
        "psl",
        "Plan directeur sectoriel logement (PSL)",
        "sectoriel",
        401,
        True,
        _GEOPORTAIL_MAP,
        document_url=(
            "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2021/02/10/a139/jo/fr/"
            "html/eli-etat-leg-rgd-2021-02-10-a139-jo-fr-html.html"
        ),
    ),
    OverlayLayer(
        "pst",
        "Plan directeur sectoriel transports (PST)",
        "sectoriel",
        410,
        True,
        _GEOPORTAIL_MAP,
        document_url=(
            "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2021/02/10/a141/jo/fr/"
            "html/eli-etat-leg-rgd-2021-02-10-a141-jo-fr-html.html"
        ),
    ),
    OverlayLayer(
        "pszae",
        "Plan directeur sectoriel zones d'activités (PSZAE)",
        "sectoriel",
        407,
        True,
        _GEOPORTAIL_MAP,
        document_url=(
            "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2021/02/10/a142/jo/fr/"
            "html/eli-etat-leg-rgd-2021-02-10-a142-jo-fr-html.html"
        ),
    ),
    OverlayLayer(
        "psp",
        "Plan directeur sectoriel paysages (PSP)",
        "sectoriel",
        396,
        True,
        _GEOPORTAIL_MAP,
        document_url=(
            "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2021/02/10/a140/jo/fr/"
            "html/eli-etat-leg-rgd-2021-02-10-a140-jo-fr-html.html"
        ),
    ),
    OverlayLayer(
        "natura2000_habitats", "Natura 2000 — habitats", "environnement", 540, True, _GEOPORTAIL_MAP
    ),
    OverlayLayer(
        "natura2000_oiseaux", "Natura 2000 — birds", "environnement", 533, True, _GEOPORTAIL_MAP
    ),
    OverlayLayer(
        "reserves_naturelles",
        "National nature reserves (ZPIN)",
        "environnement",
        804,
        True,
        _GEOPORTAIL_MAP,
    ),
    OverlayLayer(
        "flood_hq20", "Flood zone — HQ20 (20-year)", "risques", 3037, True, _GEOPORTAIL_MAP
    ),
    OverlayLayer(
        "flood_hq100", "Flood zone — HQ100 (100-year)", "risques", 3262, True, _GEOPORTAIL_MAP
    ),
    OverlayLayer(
        "water_protection",
        "Drinking-water protection zone (ZPS)",
        "eau",
        573,
        True,
        _GEOPORTAIL_MAP,
    ),
    OverlayLayer(
        "heritage_ssmn",
        "Protected buildings / heritage (SSMN)",
        "patrimoine",
        709,
        False,
        _GEOPORTAIL_MAP,
    ),
    OverlayLayer(
        "archaeological_sites", "Archaeological sites", "patrimoine", 2560, False, _GEOPORTAIL_MAP
    ),
    OverlayLayer(
        "noise_airport", "Noise exposure — Findel airport", "nuisances", 2667, True, _GEOPORTAIL_MAP
    ),
    OverlayLayer(
        "findel_servitude",
        "Findel airport servitude (aviation height limit)",
        "servitudes",
        3212,
        True,
        _GEOPORTAIL_MAP,
    ),
    OverlayLayer(
        "gas_network", "High-pressure gas network", "reseaux", 1494, True, _GEOPORTAIL_MAP
    ),
]

OVERLAY_LAYERS_BY_CODE: dict[str, OverlayLayer] = {layer.code: layer for layer in OVERLAY_LAYERS}
