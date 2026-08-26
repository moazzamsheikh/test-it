-- Runs once on first boot (empty data dir). Alembic re-asserts these with
-- CREATE EXTENSION IF NOT EXISTS so a fresh migrate on any DB is self-sufficient.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- fuzzy address matching (M1.2)
CREATE EXTENSION IF NOT EXISTS unaccent;     -- accent-insensitive street names (M1.2)
CREATE EXTENSION IF NOT EXISTS vector;       -- embeddings (M2.3 / M3)
