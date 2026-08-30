# Alix — Luxembourg Parcel Intelligence Platform
# Interim dev targets. `make ingest` / `make demo` land with M2 and the seed set.

.PHONY: db-up db-down migrate downgrade revision lint format typecheck test seed-reference

HOST_DB_URL ?= postgresql+psycopg://alix:change_me_local_only@localhost:5433/alix

db-up:  ## Start the PostGIS+pgvector database
	docker compose up -d db

db-down:  ## Stop all services
	docker compose down

migrate:  ## Apply migrations to head (host -> compose db on :5433)
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/alembic upgrade head

downgrade:  ## Roll back one migration
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/alembic downgrade -1

revision:  ## Autogenerate a migration: make revision m="message"
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/alembic revision --autogenerate -m "$(m)"

lint:  ## ruff + black check
	cd backend && .venv/bin/ruff check app alembic ingestion && .venv/bin/black --check app alembic ingestion

format:  ## ruff --fix + black write
	cd backend && .venv/bin/ruff check app alembic ingestion --fix && .venv/bin/black app alembic ingestion

typecheck:  ## mypy strict on the backend package
	cd backend && .venv/bin/mypy app ingestion

test:  ## pytest
	cd backend && .venv/bin/pytest

seed-reference:  ## Load communes, cadastral crosswalk, parcel/building natures
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/python -m ingestion.seed_reference_data
