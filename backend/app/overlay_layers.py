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
    # For layers governed per-watercourse/per-commune rather than by one
    # national document (flood zones: a separate RGD per river basin, not
    # the single "PGRI" planning document originally assumed — see
    # DECISIONS.md), a static admin_commune_code -> Legilux URL mapping,
    # verified against the real government legislation page for each of
    # our two target communes specifically. Does not scale to Luxembourg's
    # other ~100 communes without more entries — a known, already-tracked
    # gap (see PROGRESS.md's 102-commune scaling analysis), not a hidden one.
    document_url_by_commune: dict[str, str] | None = None
    # For layers whose own GetFeatureInfo attributes carry a direct
    # per-feature Legilux link (ZPIN's real `lien_legilux` field — verified
    # live, not assumed; Natura 2000 checked the same way and does NOT have
    # one, so it still needs a static lookup instead), the `detail` dict key
    # holding that link. Resolved dynamically at request time, not listed
    # here statically — see app/services/legilux_dynamic.py.
    document_url_detail_key: str | None = None
    # For layers where each real feature is designated by its OWN separate
    # RGD, but (unlike ZPIN) the feature's own attributes carry only an
    # identifying code (Natura 2000's real `SITECODE`), not a direct link —
    # a static SITECODE -> Legilux URL mapping, verified against the real
    # government site list for every site intersecting our two target
    # communes specifically (see DECISIONS.md). Same "known instance" scope
    # limit as `document_url_by_commune`: doesn't cover Luxembourg's other
    # real Natura 2000 sites nationally without more entries.
    document_url_by_sitecode: dict[str, str] | None = None


_GEOPORTAIL_MAP = "https://map.geoportail.lu/theme/main"

# Verified against eau.gouvernement.lu's own legislation page (the real
# per-watercourse RGD list, not a plausible-looking guess): each real RGD
# is dated 30 March 2022 and names its own river basin explicitly. "0304"
# (Luxembourg City, on the Alzette) -> a188 "Alzette et Wark"; "0807"
# (Wiltz, on the Wiltz river) -> a187 "Sûre supérieure, de la Wiltz, de la
# Clerve et de l'Our" — confirmed by fetching and reading the real extracted
# title, not by trusting a summarised numbering (an earlier AI-summarised
# fetch of the same source page misattributed a185 to Wiltz; a185 is
# actually "Mamer et Eisch" — see DECISIONS.md).
_FLOOD_DOCUMENT_URLS = {
    "0304": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2022/03/30/a188/jo/fr/"
        "html/eli-etat-leg-rgd-2022-03-30-a188-jo-fr-html.html"
    ),
    "0807": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2022/03/30/a187/jo/fr/"
        "html/eli-etat-leg-rgd-2022-03-30-a187-jo-fr-html.html"
    ),
}

# Verified directly against environnement.public.lu's own real Natura 2000
# site table (fetched and parsed by hand, not an AI-summarized read — see
# DECISIONS.md on why that distinction matters) — every SITECODE below was
# confirmed live to intersect a real parcel in one of our two target
# communes, and every document_url below was fetched and its real extracted
# title checked to match the expected site name exactly (e.g. LU0001018 ->
# "Vallée de la Mamer et de l'Eisch") before being added here.
_NATURA2000_HABITATS_DOCUMENT_URLS = {
    "LU0001018": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2025/06/13/a242/jo/fr/"
        "html/eli-etat-leg-rgd-2025-06-13-a242-jo-fr-html.html"
    ),
    "LU0001022": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2022/10/28/a548/jo/fr/"
        "html/eli-etat-leg-rgd-2022-10-28-a548-jo-fr-html.html"
    ),
    "LU0001026": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2023/10/06/a647/jo/fr/"
        "html/eli-etat-leg-rgd-2023-10-06-a647-jo-fr-html.html"
    ),
    "LU0001005": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2023/05/24/a261/jo/fr/"
        "html/eli-etat-leg-rgd-2023-05-24-a261-jo-fr-html.html"
    ),
    "LU0001006": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2023/05/24/a262/jo/fr/"
        "html/eli-etat-leg-rgd-2023-05-24-a262-jo-fr-html.html"
    ),
}

_NATURA2000_BIRDS_DOCUMENT_URLS = {
    "LU0002017": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2023/10/06/a644/jo/fr/"
        "html/eli-etat-leg-rgd-2023-10-06-a644-jo-fr-html.html"
    ),
    "LU0002007": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2023/10/06/a661/jo/fr/"
        "html/eli-etat-leg-rgd-2023-10-06-a661-jo-fr-html.html"
    ),
    "LU0002013": (
        "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2023/05/24/a275/jo/fr/"
        "html/eli-etat-leg-rgd-2023-05-24-a275-jo-fr-html.html"
    ),
}

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
        "natura2000_habitats",
        "Natura 2000 — habitats",
        "environnement",
        540,
        True,
        _GEOPORTAIL_MAP,
        document_url_by_sitecode=_NATURA2000_HABITATS_DOCUMENT_URLS,
    ),
    OverlayLayer(
        "natura2000_oiseaux",
        "Natura 2000 — birds",
        "environnement",
        533,
        True,
        _GEOPORTAIL_MAP,
        document_url_by_sitecode=_NATURA2000_BIRDS_DOCUMENT_URLS,
    ),
    OverlayLayer(
        "reserves_naturelles",
        "National nature reserves (ZPIN)",
        "environnement",
        804,
        True,
        _GEOPORTAIL_MAP,
        document_url_detail_key="lien_legilux",
    ),
    OverlayLayer(
        "flood_hq20",
        "Flood zone — HQ20 (20-year)",
        "risques",
        3037,
        True,
        _GEOPORTAIL_MAP,
        document_url_by_commune=_FLOOD_DOCUMENT_URLS,
    ),
    OverlayLayer(
        "flood_hq100",
        "Flood zone — HQ100 (100-year)",
        "risques",
        3262,
        True,
        _GEOPORTAIL_MAP,
        document_url_by_commune=_FLOOD_DOCUMENT_URLS,
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
        # Art. 19-28 of this RGD are specifically the height/radio-navigation
        # servitudes this layer represents — confirmed by reading the real
        # extracted article text, not assumed from the POS's general title
        # (see DECISIONS.md).
        document_url=(
            "https://data.legilux.public.lu/filestore/eli/etat/leg/rgd/2006/05/17/n1/jo/fr/"
            "html/eli-etat-leg-rgd-2006-05-17-n1-jo-fr-html.html"
        ),
    ),
    OverlayLayer(
        "gas_network", "High-pressure gas network", "reseaux", 1494, True, _GEOPORTAIL_MAP
    ),
]

OVERLAY_LAYERS_BY_CODE: dict[str, OverlayLayer] = {layer.code: layer for layer in OVERLAY_LAYERS}
