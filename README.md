# Luxembourg Parcel Intelligence Platform

Spatial + regulatory data platform for architects: given a Luxembourg cadastral
parcel, resolve the regulations that apply to it and answer questions about it
with citations to official sources.

> **Status: foundation stage.** The database platform and the provenance schema
> that every later module queries are built and verified. Modules M1–M5 are not
> yet implemented. This README is kept honest — it describes what actually runs
> today, not what is planned. See [Roadmap](#roadmap) for what comes next.

---

## What works today

| Capability | Status |
|---|---|
| PostGIS + pgvector database, one command up on a clean machine | ✅ |
| EPSG:2169 (LUREF) ↔ WGS84 reprojection, verified correct | ✅ |
| Provenance schema (sources / documents / chunks), migrated & reversible | ✅ |
| Ready for hybrid search (vector + full-text) and geospatial queries | ✅ (schema) |
| `mypy --strict` + ruff + black clean | ✅ |
| M1 map/cadastre/addresses · M2 ingestion · M3 chatbot · M4 report · M5 procedures | ⛔ not yet |

---

## Quickstart (zero to running)

**Prerequisites:** Docker + Docker Compose, and Python 3.11+ (for running
migrations from the host).

```bash
# 1. Configure environment
cp .env.example .env            # local defaults work as-is; no secrets required

# 2. Start the database (builds a custom PostGIS + pgvector image on first run)
make db-up                      # or: docker compose up -d db

# 3. Set up the backend toolchain and apply the schema
cd backend
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cd ..
make migrate                    # applies Alembic migrations to head

# 4. Verify the coordinate reprojection is correct
docker compose exec db psql -U alix -d alix -c \
  "SELECT ST_AsText(ST_Transform(ST_SetSRID(ST_MakePoint(6.131935,49.611622),4326),2169));"
# Expect a LUREF point near POINT(77384 75222) — the correct grid range for Lux City.
```

The database is exposed on **`localhost:5433`** (mapped from container `5432`, to
avoid colliding with a local Postgres).

Useful targets: `make lint`, `make typecheck`, `make test`, `make downgrade`,
`make revision m="message"`.

---

## Architecture

### One database for geography *and* semantics
A single **PostgreSQL 16** instance carries both **PostGIS** (geometry, spatial
indexes, coordinate reprojection) and **pgvector** (embedding similarity search).
This is deliberate: parcel-scoped retrieval must filter by *geography* and
*metadata* in the same query that runs the *vector* search. A separate vector
database would force cross-system joins.

No official image ships both extensions, so we build a small custom image from
`postgis/postgis:16-3.4` and add `postgresql-16-pgvector` from the PGDG apt repo
(see [`docker/postgres/Dockerfile`](docker/postgres/Dockerfile)).

### Provenance-first data model
The product's core promise is *"every claim carries a source"* — an uncited
answer is worthless here. So the schema was designed before any crawler, to make
provenance structurally impossible to omit. Three tables
([`backend/app/models/provenance.py`](backend/app/models/provenance.py)):

- **`sources`** — the crawl registry. Holds incremental-fetch state
  (`etag`, `last_modified`, `last_content_hash`) and observability fields
  (`last_success_at`, `last_status`, `failure_count`, `documents_ingested`).
- **`documents`** — one fetched artifact, the authoritative provenance record:
  `source_url`, `fetched_at`, `publisher`, `document_date`, `sha256`, `language`,
  `commune_code`, `legal_status`, `document_type`, `eli`. Amendment chains are
  modelled with self-referential `supersedes_id` / `superseded_by_id`.
  Idempotency via `UNIQUE(source_url, sha256)`.
- **`chunks`** — retrievable passages with an `embedding vector(1024)` (HNSW
  cosine index) and a generated `tsvector` (GIN index) for hybrid search. Chunks
  **denormalise** the key filter fields (`commune_code`, `language`,
  `legal_status`, `document_date`, `document_type`) so retrieval filters the
  search space *before* scoring and excludes repealed text without a join.

### Coordinate systems
Source geodata is **EPSG:2169** (LUREF / Luxembourg 1930 Gauss); browser/user
input is **WGS84 (EPSG:4326)**. Reprojection is always **explicit** via PostGIS
`ST_Transform`, never implicit. Verified: a Luxembourg-City point round-trips
4326→2169→4326 with **0.0003 m** error. PROJ runs offline
(`NETWORK_ENABLED=OFF`), so transforms are deterministic.

---

## Technical choices

| Choice | Why | Alternative rejected |
|---|---|---|
| PostgreSQL + PostGIS + pgvector (one DB) | Geo + vector + metadata filter in one query | Separate vector DB (cross-system joins) |
| Custom PostGIS+pgvector Docker image | No official image has both | Two databases / unofficial image |
| Denormalised filter fields on chunks | Filter before scoring; exclude repealed w/o join | Fully normalized (join before vector scan) |
| Amendment chains as self-FKs + `legal_status` | Right-sized; enables "version in force" queries | Separate versions table (heavier) |
| ELI nullable-unique, UUID primary key | Communal PDFs/geodata have no ELI | ELI-as-PK (mixed PK strategy) |
| Plain typed ingestion scripts | Small serial batch corpus | Prefect/Dagster (ops overhead now) |
| `embedding vector(1024)`, multilingual model | FR/DE/LB coverage; self-hostable (cost = compute) | 3072-d API model (cost, no LB) |
| `legal_status` defaults to `unknown` | Honest ingest-time state; never guess `in_force` | Default in_force (risks citing repealed) |

The full decision log with reasoning and rejected alternatives is in
[DECISIONS.md](DECISIONS.md).

---

## Repository layout

```
docker/postgres/        Custom PostGIS+pgvector image + first-boot extension SQL
docker-compose.yml      db service (host :5433)
Makefile                db-up, migrate, lint, typecheck, test, …
backend/
  app/core/             Settings (Pydantic) + async SQLAlchemy engine
  app/models/           ORM models: provenance schema + controlled enums
  alembic/              Migrations (env.py filters PostGIS-owned tables)
  pyproject.toml        Deps + ruff/black/mypy/pytest config
```

---

## Current limitations (honest status)

- **No ingestion, map, retrieval, report, or procedure logic yet.** Only the
  database platform and provenance schema exist.
- Migrations are run from a host virtualenv (`backend/.venv`); a containerised
  backend service and `make ingest` / `make demo` land with M2.
- Embedding dimension is pinned to 1024; changing the model to another dimension
  is an explicit migration.
- Production use of the Luxembourg geoportal (`ws.geoportail.lu`) requires ACT
  domain approval — to be documented, not a blocker for the assessment.

---

## Roadmap

1. **M1 — Map, cadastre, addresses**: spatial schema (parcels in EPSG:2169,
   addresses with trigram/unaccent fuzzy search, a generic config-driven overlay
   table), ingest real PCN + BD-Adresses for two contrasting communes
   (Luxembourg City + Wiltz), parcel identification, regulatory overlays.
2. **M2 — Ingestion & provenance**: national legislation via the Legilux SPARQL
   endpoint (in-force versions only), the two communes' PAG/PAP/building bylaws,
   idempotent + incremental pipeline, status dashboard.
3. **M4 — Report + PDF**, then **M3 — Hybrid retrieval + chatbot + eval harness**.
4. **M5 — Procedure assistant**: only if time remains.

Deliverables to accompany the code: `SOURCES.md`, `SCALING.md`, `EVAL.md`, and a
weekly `PROGRESS.md`.

---

## Notes

- Secrets live in `.env` (gitignored); `.env.example` holds placeholders only.
- Official texts always prevail over any output of this system.
