"""Shared constants for the M1 ingestion scripts."""

from __future__ import annotations

from pathlib import Path

# Administrative commune names to deep-ingest (see DECISIONS.md: contrasting
# profile — Luxembourg City large/complex, Wiltz small/north).
TARGET_ADMIN_COMMUNES = ["Wiltz", "Luxembourg"]

USER_AGENT = (
    "AlixIntelligence-Assessment/0.1 (assessment research; contact: alixmoazzam@hotmail.com)"
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
PAG_ZIP_URLS: dict[str, str] = {
    "0304": "https://download.data.public.lu/resources/pag-ville-de-luxembourg/20260722-220507/pag-c026.zip",
    "0807": "https://download.data.public.lu/resources/pag-wiltz/20260326-230844/pag-c023.zip",
}

# Project-root-level cache for bulk downloads — gitignored (see .gitignore's
# `data/` rule), NOT backend/app/reference_data/ (that's for small, tracked,
# hand-curated vocabularies, a different thing — see DECISIONS.md).
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
