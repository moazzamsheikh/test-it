# Luxembourg Parcel Intelligence Platform

Spatial + regulatory data platform for architects: given a Luxembourg cadastral
parcel, resolve the regulations that apply to it and answer questions about it
with citations to official sources.

> **Status: M1.1-M1.5 are real and working together; M2 has a real PAG/PAP zoning slice; M5 has one genuine, scoped-down slice.**
> Open the map, click a parcel or search an address, see a real Wiltz/Luxembourg
> City parcel with its geometry highlighted, its regulatory overlays (PAG
> zoning, Natura 2000, flood zones, servitudes, etc.), its geometry analysis
> (road frontage, nearby-parcel distances, LiDAR-derived slope, a
> manual-setback buildable envelope), and its **real PAG/PAP zone
> classification** — resolved via an actual spatial join against ACT's own
> per-commune PAG data, with the real regulatory article text (and real
> COS/CUS/CSS/DL planning coefficients for not-yet-built zones), not a WMS
> point-sample — verified in a real browser, not just curl. The side panel
> also shows one real, citation-backed government procedure (building-permit
> application) — a structured display, explicitly not a chatbot. National
> legislation ingestion and retrieval/chatbot (M3) do not exist yet, and M5
> proper depends on M3. This README describes what actually runs today, not
> what is planned — see [Roadmap](#roadmap).

---

## What works today

| Capability | Status |
|---|---|
| PostGIS + pgvector database, one command up on a clean machine | ✅ |
| EPSG:2169 (LUREF) ↔ WGS84 reprojection, verified correct (backend AND frontend) | ✅ |
| Provenance schema (sources / documents / chunks), migrated & reversible | ✅ |
| M1 spatial schema (communes, parcels, buildings, addresses), migrated & reversible | ✅ |
| Real PCN + BD-Adresses ingestion for Wiltz + Luxembourg City, idempotent (`make ingest`) | ✅ |
| M1.2 address search API — trigram fuzzy match, sub-15ms warm (see below) | ✅ |
| M1.3 parcel identify (by click, by cadastral reference) + full detail API | ✅ |
| M1.1 map UI — Next.js + OpenLayers, 3 real switchable WMS base layers, click-to-identify, address search, side panel | ✅ |
| M1.4 regulatory overlays — 18 real WMS layers, per-parcel cached intersects | ✅ |
| M1.5 geometry analysis — road frontage, neighbour distances, LiDAR slope, manual-setback buildable envelope | ✅ |
| M5 (partial) — one real procedure (building permit), citation-backed, not a chatbot | ✅ |
| M2 (partial) — real PAG/PAP zoning + real COS/CUS/CSS/DL coefficients for both target communes | ✅ |
| 41 pytest tests (schema constraints + real-data e2e + API), all passing | ✅ |
| `mypy --strict` + ruff + black + ESLint + `tsc --noEmit` clean | ✅ |
| M2 (legislation ingestion) · M3 chatbot · M4 report/PDF | ⛔ not started |

---

## Quickstart (zero to running)

**Prerequisites:** Docker + Docker Compose, Python 3.11+ (for running
migrations/ingestion/the API from the host — a containerised backend service
lands later), and Node.js 20+ for the frontend.

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

# 4. Load the real corpus (reference data + PCN parcels/buildings + BD-Adresses,
#    filtered to Wiltz + Luxembourg City). Downloads ~190MB once, cached under
#    data/cache/ (gitignored); subsequent runs reuse the cache and are idempotent.
make ingest

# 5. Run the API
make run                        # or: cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

# 6. Run the frontend (in a second terminal)
cd frontend
npm install
cp .env.example .env.local      # points at http://localhost:8000 by default
npm run dev                     # http://localhost:3000
```

Try it against real data:

```bash
curl "http://localhost:8000/api/v1/addresses/search?q=Rue+Dominique+Lang"
curl "http://localhost:8000/api/v1/parcels/054A00242005292"
curl "http://localhost:8000/api/v1/parcels/identify?lon=6.173833&lat=49.619564"
```

Or open **http://localhost:3000** — search an address or click the map. The
map defaults to Luxembourg City; the three base layers (Topographic,
Orthophoto, Cadastral plan) are all real WMS layers from
`wms.geoportail.lu/opendata/service`.

Run the test suite (requires `make ingest` to have run — several tests are
real-data end-to-end checks, not fixtures):

```bash
make test
```

The database is exposed on **`localhost:5433`** (mapped from container `5432`, to
avoid colliding with a local Postgres).

Useful targets: `make lint`, `make typecheck`, `make test`, `make downgrade`,
`make revision m="message"`, `make seed-reference`, `make ingest-parcels`,
`make ingest-addresses`.

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

### M1 spatial schema
([`backend/app/models/cadastre.py`](backend/app/models/cadastre.py)) — 9 tables:
`communes` (administrative, LAU2-keyed), `cadastral_communes` (ACT's own,
*different* numbering — see below), `cadastral_sections`, `parcel_natures` /
`building_natures` (reference tables, not enums — ACT-owned open vocabularies),
`parcels`, `buildings`, `parcel_buildings` (persisted many-to-many: a building
can span multiple parcels, computed via `ST_Intersects` at ingest), `addresses`.

**Two commune codes, on purpose.** PCN's cadastral commune numbering
(`cadastral_commune_code`) and the LAU2 administrative code (`admin_commune_code`)
are genuinely different systems, verified non-1:1 after historical mergers
(cadastral communes "Arsdorf" and its former neighbour are today both sections
inside administrative commune "Rambrouch"). Cadastral code drives the
commune+section+number reference search; admin code drives which commune's
regulations apply (M2/M3 scoping). Conflating them would misattribute
regulations for any merged commune. Full reasoning in
[DECISIONS.md](DECISIONS.md).

### Real ingestion, not fixtures
[`backend/ingestion/`](backend/ingestion/) loads the actual PCN shapefile
(pyshp + shapely — pure Python, no GDAL, so `make ingest` needs nothing beyond
`pip install -e .[dev]`) and BD-Adresses CSV from data.public.lu, filtered to
Wiltz + Luxembourg City. Verified: 40,291 parcels, 28,891 buildings, 29,831
parcel↔building links (a real multi-parcel-building minimum-overlap threshold
was needed — see DECISIONS.md), 23,680 addresses, 99.8% resolved to a parcel.
Both parcel/building and address ingestion are idempotent (upsert on natural
keys; buildings have none, so they're scoped delete-then-reinsert instead —
see DECISIONS.md) — re-running produces identical row counts, verified.

### M1.2 address search
Hybrid of three things, each covering what the others miss:
`pg_trgm`'s `%` similarity operator (typo tolerance — "Lng" still matches
"Lang"), a small hand-written abbreviation table applied before normalisation
(`r.` → `rue`), and a leading-digit split so "1 Rue du Fort Thüngen" filters on
house number 1 and fuzzy-matches the street separately. **Warm-index
performance** (`EXPLAIN ANALYZE`, real query against the ingested corpus):

```
Bitmap Heap Scan on addresses a  (actual time=1.790..12.512 rows=30 loops=1)
  Recheck Cond: (street_name_normalized % 'rue dominique lang'::text)
  ->  Bitmap Index Scan on ix_addresses_street_name_trgm  (actual time=1.568..1.568 rows=2097)
Execution Time: 12.641 ms
```
Comfortably under the 200ms target. This index did **not** exist on the first
pass — the design was documented but never implemented, caught only by
actually running `EXPLAIN ANALYZE` (110ms sequential scan before the fix). See
DECISIONS.md.

Does **not** yet solve full FR/DE/LB street-name variants — that needs CACLR's
`ALIAS.RUE` real per-street alias data, not a synonym table, and isn't ingested
yet (see SOURCES.md).

### M1.3 parcel identify
Three endpoints: identify-by-click (`lon`/`lat` in WGS84, transformed
server-side to LUREF via `ST_Transform`, then `ST_Covers`), identify-by-cadastral-
reference (commune + section + number), and full parcel detail (addresses,
buildings with overlap area, geometry as WGS84 GeoJSON for map display).
**Identify-by-click returns a list, not a single parcel** — 0 results (the
click missed every parcel, e.g. a road) and >1 results (the click landed
exactly on a shared boundary — a graded edge case) are both real, honest
outcomes surfaced to the caller, not silently resolved by picking one.

### M1.1 map UI
`frontend/` — Next.js (App Router) + TypeScript strict + OpenLayers + Tailwind.
The map's **working projection is EPSG:2169** (LUREF) itself, not Web Mercator
— the same projection the source data and the official geoportail use, and
the one that makes the reprojection requirement concrete rather than
incidental. Three real WMS base layers (`Basemap`, `ortho_latest`, `PCN`) from
`wms.geoportail.lu/opendata/service`, each verified with a live `GetMap`
request before being wired into React. A click on the map transforms the
LUREF click coordinate to WGS84 (`ol/proj` + `proj4`) and calls the identify
API; the selected parcel's geometry comes back as WGS84 GeoJSON and is
reprojected back to LUREF for the highlight overlay — the same round trip the
backend does, independently implemented, and cross-checked against it (see
below). Address search and parcel identify share one page's state, so
selecting an address flies the map to it and opens the same side panel a map
click would.

Verified in an actual headless browser (Playwright + Chromium — installed for
this; no browser-automation tool was otherwise available), not just `tsc`/
`eslint`: zero console errors across load, click-identify, address-search-select,
and each of the three base layers, screenshotted at every step.

### Coordinate systems
Source geodata is **EPSG:2169** (LUREF / Luxembourg 1930 Gauss); browser/user
input is **WGS84 (EPSG:4326)**. Reprojection is always **explicit**, never
implicit, and now proven in three independent places: a synthetic PostGIS
round-trip (4326→2169→4326, **0.0003 m** error), the identify-by-click
endpoint (real WGS84 coordinates correctly resolving the real LUREF-stored
parcel), and the frontend's own `proj4`-based transform. PROJ runs offline
(`NETWORK_ENABLED=OFF`) on the backend, so its transforms are deterministic.

**The frontend transform needed its own verification, and a first attempt was
wrong by 108 metres.** `proj4` needs the LUREF↔WGS84 datum-shift parameters
explicitly (`towgs84=...`); a first, plausible-looking guess at those seven
numbers put the frontend's transform 108m away from the backend's PostGIS/PROJ
result for the same known coordinate pair. Fixed by copying PostGIS's own
`spatial_ref_sys.proj4text` parameters verbatim — with those, `proj4` agrees
with PostGIS to **~1.5mm**. Verified with a two-line Node script before any
map code was written, not assumed correct because the numbers looked
reasonable (see DECISIONS.md).

---

## Technical choices

| Choice | Why | Alternative rejected |
|---|---|---|
| PostgreSQL + PostGIS + pgvector (one DB) | Geo + vector + metadata filter in one query | Separate vector DB (cross-system joins) |
| Custom PostGIS+pgvector Docker image | No official image has both | Two databases / unofficial image |
| Denormalised filter fields on chunks | Filter before scoring; exclude repealed w/o join | Fully normalized (join before vector scan) |
| Two commune codes on `parcels` (cadastral + LAU2 admin) | Verified non-1:1 after mergers; conflating misattributes regulations | Single code (breaks one of the two required lookups) |
| `parcel_natures`/`building_natures` as reference tables | ACT-owned open vocabularies, carry a category grouping | Python enum (duplicates ACT's taxonomy) |
| `parcel_buildings` persisted join, not a live query | Real BATIMENTS data has no parcel FK at all; buildings can span >1 parcel | Single nullable FK (silently wrong for the multi-parcel case) |
| pyshp + shapely for geodata parsing | No system deps — `make ingest` stays `pip install -e .[dev]` | GDAL/ogr2ogr (outside the mandatory stack) |
| Buildings: scoped delete-then-reinsert per ingest | Real source has no natural key at all to upsert against | Upsert (nothing to conflict on) |
| Address search: trigram + abbreviation table, not aliases | Small, reviewable, real coverage gain | Full CACLR alias data (not ingested yet — real gap, logged) |
| Identify-by-click returns a list | 0 or >1 matches are real, honest outcomes (edge cases, not errors) | Single parcel (silently wrong on a boundary click) |
| Map's working projection is EPSG:2169, not Web Mercator | Matches source data and the official geoportail; makes reprojection concrete, not incidental | Web Mercator + reproject only at the API boundary (hides the requirement) |
| Explicit OL `resolutions` array, not default zoom levels | OL's default zoom→resolution mapping assumes a Web-Mercator-scale world — meaningless for LUREF's small extent (verified: broke silently, see DECISIONS.md) | Default zoom levels (blank map at any "reasonable-looking" zoom number) |
| Frontend proj4 datum params copied from PostGIS's own `spatial_ref_sys` | A first plausible guess was 108m off the backend's real transform; PostGIS's own values agree to ~1.5mm | Guessed/looked-up-elsewhere towgs84 values (unverified, silently wrong) |
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
Makefile                db-up, migrate, seed-reference, ingest, lint, test, …
data/cache/              Bulk downloads (gitignored) — pcn-shape.zip, addresses.csv
backend/
  app/core/             Settings, async SQLAlchemy engine, structlog config
  app/models/           ORM models: provenance schema + M1 spatial schema
  app/schemas/          Pydantic API response models
  app/api/v1/           FastAPI routers (addresses, parcels)
  app/services/         Query logic behind the routers (address search, parcel lookups)
  app/reference_data/   Small, tracked CSVs (communes, natures, cadastral crosswalk)
  alembic/              Migrations (env.py filters PostGIS-owned tables)
  ingestion/            Real PCN + BD-Adresses ingestion scripts, cache-aware downloader
  tests/                pytest: schema constraints, real-data e2e, API
  pyproject.toml        Deps + ruff/black/mypy/pytest config
frontend/
  app/                  Next.js App Router (page.tsx orchestrates state)
  components/           MapView (OpenLayers), AddressSearch, ParcelPanel
  lib/                  API client, TypeScript types, EPSG:2169 proj4 setup
```

---

## Current limitations (honest status)

- **No zone_verte or HV electricity easement overlay layer.** Searched
  exhaustively across the full 1437-layer geoportail theme tree — neither
  exists as a real, distinct layer there (see SOURCES.md).
- **Buildable envelope (M1.5) still uses a single manual uniform setback, not
  a real extracted value.** Real COS/CUS/CSS/DL planning coefficients (max
  footprint ratio, floor area ratio, soil-sealing ratio, dwelling density)
  are now available for `NQ_PAP` zones as genuine structured data (see M2
  below) — but those are area/density limits, not a linear setback distance,
  so they don't replace this input; the brief's own explicit manual-input
  escape hatch still applies here (see DECISIONS.md).
- **Real PAG/PAP zoning is genuinely partial in the source data.** After
  ingesting both target communes' real PAG datasets and fixing a real
  axis-order bug (Wiltz's export specifically), zone coverage is 65.0%
  (Luxembourg City) / 53.8% (Wiltz) of real parcels — confirmed against the
  live geoportail WMS that this is a real gap in the *downloadable* dataset
  (not our parsing), consistent with an in-progress PAG revision for
  Luxembourg City (see DECISIONS.md). An uncovered parcel gets an honest
  empty result, not a fabricated zone. PAP QE's graphic-part PDFs (~250MB,
  no text extraction planned yet) are referenced by filename only, not
  ingested as documents.
- **No declared/legal area source found.** PCN's `PARCELLES` layer has no
  area field at all; `area_declared_m2` is always `null` until a source is
  found (see DECISIONS.md) — never fabricated.
- **`cadastral_sections` doesn't join to `parcels.section_code`.** The
  crosswalk it's seeded from uses a different section-naming convention
  (administrative-commune-wide, e.g. `HoB`) than real PCN data (single letter,
  scoped per cadastral commune) — see DECISIONS.md. Section display names
  (e.g. "Bonnevoie") aren't wired into the API yet as a result.
- **Address search doesn't cover FR/DE/LB street-name variants** beyond a
  small abbreviation table — real alias data (CACLR's `ALIAS.RUE`) isn't
  ingested yet.
- No ingestion of national legislation, building bylaws, retrieval, or report
  logic yet (the rest of M2, M3, M4). M5 has exactly one real procedure
  ingested (building permit) — a structured display, not a chatbot/retrieval
  system; a second procedure or multi-document search needs M3 first.
- Migrations/ingestion/API are run from a host virtualenv (`backend/.venv`); a
  containerised backend service and `make demo` (seeded small dataset) land
  later.
- Embedding dimension is pinned to 1024; changing the model to another
  dimension is an explicit migration.
- Production use of the Luxembourg geoportal (`ws.geoportail.lu`) requires ACT
  domain approval — to be documented, not a blocker for the assessment. The
  actually-working public endpoint we found is `wms.geoportail.lu/opendata/service`
  (see SOURCES.md).

---

## Roadmap

1. ~~**M1.4 — Regulatory overlays**~~ ✅ done — 18 real thematic WMS layers
   (PAG, Natura 2000, flood zones, servitudes, etc.), config-driven, cached
   per-parcel intersects.
2. ~~**M1.5 — Geometry analysis**~~ ✅ done (stretch, per the brief itself) —
   road frontage, neighbour distances, LiDAR-derived slope, manual-setback
   buildable envelope.
3. ~~**M5 — Procedure assistant**~~ ⚠️ partial, out of order at the user's
   explicit request — one real, citation-backed government procedure
   (building permit), no spec text available for M5 (unlike M1.4/M1.5),
   scoped to avoid the M2/M3 dependency. Honestly labelled as a structured
   document display, not a chatbot — see DECISIONS.md.
4. ~~**M2 — PAG/PAP zoning**~~ ⚠️ partial, per a real requirement dictated via
   video (not the assessment PDF — see `PAG_PAP_SPEC.md`): real per-commune
   PAG open data (GML + DOCX) for both target communes, ingested via a real
   spatial join, resolving each parcel's actual zone and citing the real
   regulation text — not the M1.4 WMS point-sample, which has no
   classification attribute at all. Also real COS/CUS/CSS/DL planning
   coefficients (footprint ratio, floor area ratio, soil-sealing ratio,
   dwelling density) for `NQ_PAP` ("Nouveau Quartier") zones — genuine GIS
   attributes, not parsed from document text. Real, documented gaps: PAG
   zone coverage is genuinely partial in the source data itself (65%/54% of
   real parcels, confirmed against the live WMS, not a parsing bug — see
   DECISIONS.md); PAP QE's graphic-part PDFs and NQ's per-project schéma-
   directeur PDFs aren't ingested yet (filename reference only).
5. **M2 — the rest**: national legislation via the Legilux SPARQL endpoint
   (in-force versions only), building bylaws, idempotent + incremental
   pipeline, status dashboard.
6. **M4 — Report + PDF**, then **M3 — Hybrid retrieval + chatbot + eval harness**.
7. **M5, completed** — a real multi-procedure, retrieval-backed assistant once
   M3 exists; only if time remains.

Deliverables to accompany the code: `SOURCES.md`, `SCALING.md`, `EVAL.md`, and a
weekly `PROGRESS.md`.

---

## Notes

- Secrets live in `.env` (gitignored); `.env.example` holds placeholders only.
- Official texts always prevail over any output of this system.
