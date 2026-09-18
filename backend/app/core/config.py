"""Application settings, loaded from environment / .env.

Precedence (pydantic-settings default): OS env vars > .env file > defaults.
So host tooling can override DATABASE_URL to localhost:5433 while the
containerised backend uses the compose value (db:5432) from .env.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# BUG (found while wiring M3's Gemini key): `env_file=".env"` resolves
# relative to the process's CWD. Every host-run ingestion script and `make`
# target in this project runs from `backend/`, but `.env` has only ever
# lived at the repo root (one level up) — so it was silently never being
# read outside of Docker Compose (which auto-loads it for var substitution,
# a separate mechanism from this Settings class). Real effect confirmed
# live: `crawler_user_agent` had been falling back to the class default the
# whole time, not the more descriptive real value in `.env`, for every
# host-run script since M1. Anchoring to this file's own location makes it
# CWD-independent.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    # Default targets the host-facing compose port so `alembic` runs out of the box.
    database_url: str = "postgresql+psycopg://alix:change_me_local_only@localhost:5433/alix"

    crawler_user_agent: str = "AlixIntelligence-Assessment/0.1"
    crawler_rate_limit_rps: float = 1.0

    llm_provider: str = "gemini"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # M3.1 — embedding model for dense retrieval. Originally planned as a
    # self-hosted multilingual model (BGE-m3/e5-large class, see the
    # 1024-d column already pinned in app/models/provenance.py::EMBEDDING_DIM)
    # but sentence-transformers/torch and onnxruntime both currently ship no
    # wheels for this environment's Python 3.14 — a verified, not assumed,
    # blocker (see DECISIONS.md). Pivoted to Gemini's own embedding model,
    # requested at output_dimensionality=1024 to keep the schema unchanged.
    embedding_model_name: str = "gemini-embedding-001"
    embedding_dim: int = 1024


settings = Settings()
