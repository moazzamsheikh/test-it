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

# Project-root-level cache for bulk downloads — gitignored (see .gitignore's
# `data/` rule), NOT backend/app/reference_data/ (that's for small, tracked,
# hand-curated vocabularies, a different thing — see DECISIONS.md).
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
