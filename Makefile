# Alix — Luxembourg Parcel Intelligence Platform
# Interim dev targets. A containerised backend service and `make demo` land later.

.PHONY: db-up db-down migrate downgrade revision lint format typecheck test seed-reference ingest-parcels ingest-addresses ingest run

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
	cd backend && .venv/bin/ruff check app alembic ingestion tests && .venv/bin/black --check app alembic ingestion tests

format:  ## ruff --fix + black write
	cd backend && .venv/bin/ruff check app alembic ingestion tests --fix && .venv/bin/black app alembic ingestion tests

typecheck:  ## mypy strict on the backend package
	cd backend && .venv/bin/mypy app ingestion tests

test:  ## pytest (requires `make ingest` to have run — real-data e2e tests)
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/pytest -v

seed-reference:  ## Load communes, cadastral crosswalk, parcel/building natures
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/python -m ingestion.seed_reference_data

ingest-parcels:  ## Ingest PCN parcels + buildings for the target communes
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/python -m ingestion.ingest_parcels_buildings

ingest-addresses:  ## Ingest BD-Adresses for the target communes
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/python -m ingestion.ingest_addresses

ingest: seed-reference ingest-parcels ingest-addresses  ## Rebuild the full M1 corpus from scratch

ingest-procedures:  ## Ingest the M5 building-permit procedure guide (separate from M1 — see DECISIONS.md)
	cd backend && DATABASE_URL=$(HOST_DB_URL) .venv/bin/python -m ingestion.ingest_procedure_building_permit

run:  ## Run the API dev server (requires `make ingest` for real data)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
