"""Shared constants for the M1 ingestion scripts."""

from __future__ import annotations

from pathlib import Path

# Administrative commune names to deep-ingest — the 8 named in the
# assessment brief's own M2.4 (contrasting profile: Luxembourg large/
# complex, Esch second city, Differdange/Dudelange/Sanem industrial south,
# Wiltz small/north, Schengen small/border, Junglinster rural/growing).
TARGET_ADMIN_COMMUNES = [
    "Wiltz",
    "Luxembourg",
    "Esch-sur-Alzette",
    "Differdange",
    "Dudelange",
    "Schengen",
    "Junglinster",
    "Sanem",
]

USER_AGENT = (
    "AlixIntelligence-Assessment/0.1 (assessment research; contact: moazzamxhk9@gmail.com)"
)

# data.public.lu resources are weekly-updated, so the dated snapshot URLs
# (download.data.public.lu/resources/.../20260824-.../file) expire the moment
# a new version is published — confirmed by a 404 mid-session. uData exposes a
# stable per-resource redirect instead (data.public.lu/.../r/<uuid>) that
# always resolves to the current file; use that, never a dated snapshot path.
PCN_SHAPE_ZIP_URL = "https://data.public.lu/fr/datasets/r/a43f88ba-c97b-4141-9fef-df7cb0c0f1ce"
BD_ADRESSES_CSV_URL = "https://data.public.lu/fr/datasets/r/5cadc5b8-6a7d-4283-87bc-f9e58dd771f7"

# M2 — real per-commune PAG open-data bundles (see PAG_PAP_SPEC.md for the
# research trail). Each ZIP is large (Luxembourg City ~1.95GB, Wiltz
# ~406MB) but stored uncompressed, so ingestion reads individual entries via
# HTTP range requests (ingestion/remote_zip.py) rather than downloading the
# whole archive. Keyed by our own admin_commune_code (LAU2), not ACT's own
# PAG commune code (C026/C023) — that code is stored per-row as provenance,
# but the actual parcel<->zone join is purely spatial (ST_Intersects), never
# by matching these code strings against each other.
#
# Same dated-URL-expiry risk as PCN/BD-Adresses above — confirmed live again
# today (Luxembourg City's own previously-working URL 404'd after the file
# was republished). Deliberately kept as dated URLs here rather than
# switched to the stable `r/<uuid>` redirect: a live check found HEAD-with-
# Range against that redirect doesn't confirm true Range support the way it
# does against the resolved dated URL (may well still work — genuinely
# untested under time pressure, not confirmed broken), so the lower-risk
# choice was refreshing these to their current values (verified working)
# rather than a redirect layer the range-reading code has never been proven
# against. Refresh via `data.public.lu/api/1/datasets/<slug>/` if these
# 404 again — see DECISIONS.md.
PAG_ZIP_URLS: dict[str, str] = {
    "0304": "https://data.public.lu/fr/datasets/r/af2814e6-280c-4643-94e6-dad6a706e0cb",
    "0807": "https://data.public.lu/fr/datasets/r/4f4cffbd-2823-42d4-aa1d-26458bb572cf",
    "0204": "https://data.public.lu/fr/datasets/r/31922f61-8bf3-4559-94f5-219ca12a3b20",
    "0202": "https://data.public.lu/fr/datasets/r/0909fd76-40c7-4634-b0c9-177856adcd92",
    "0203": "https://data.public.lu/fr/datasets/r/af07e040-820b-487a-bf45-3d59631b0a3f",
    "1206": "https://data.public.lu/fr/datasets/r/71678242-1326-4242-926f-a57d72878bfb",
    "1105": "https://data.public.lu/fr/datasets/r/c309f35b-469d-458e-b94c-8626b29ba5d6",
    "0213": "https://data.public.lu/fr/datasets/r/03de2e95-9ffc-45a3-8822-a226f69449b5",
}

PAG_LIVE_ZONAGE_URL = "https://features.geoportail.lu/collections/698/28/items"
PAG_LIVE_COMMUNE_CODES = {
    "0202": "C034",
    "0203": "C060",
    "0204": "C059",
    "0213": "C039",
    "0304": "C026",
    "0807": "C023",
    "1105": "C027",
    "1206": "C113",
}

# Project-root-level cache for bulk downloads — gitignored (see .gitignore's
# `data/` rule), NOT backend/app/reference_data/ (that's for small, tracked,
# hand-curated vocabularies, a different thing — see DECISIONS.md).
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
