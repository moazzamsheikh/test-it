"""Application settings, loaded from environment / .env.

Precedence (pydantic-settings default): OS env vars > .env file > defaults.
So host tooling can override DATABASE_URL to localhost:5433 while the
containerised backend uses the compose value (db:5432) from .env.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Default targets the host-facing compose port so `alembic` runs out of the box.
    database_url: str = "postgresql+psycopg://alix:change_me_local_only@localhost:5433/alix"

    crawler_user_agent: str = "AlixIntelligence-Assessment/0.1"
    crawler_rate_limit_rps: float = 1.0

    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""


settings = Settings()
