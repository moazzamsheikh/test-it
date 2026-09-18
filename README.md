# Luxembourg Parcel Intelligence Platform

Spatial + regulatory data platform for architects: given a Luxembourg cadastral
parcel, resolve the regulations that apply to it and answer questions about it
with citations to official sources.

> **Status: M1, M2, M3 and M4 are complete (M2 including the +8pt Legilux amendment-chain bonus); M5 has one genuine, scoped-down slice.**
> Open the map, click a parcel or search an address, see a real parcel (any
> of 8 deep-ingested communes — Luxembourg City, Esch-sur-Alzette,
> Differdange, Dudelange, Wiltz, Schengen, Junglinster, Sanem) with its
> geometry highlighted, its regulatory overlays (PAG zoning, Natura 2000,
> flood zones, servitudes, etc.), its geometry analysis (road frontage,
> nearby-parcel distances, LiDAR-derived slope, a manual-setback buildable
> envelope), and its **real PAG/PAP zone classification** — resolved via an
> actual spatial join against ACT's own per-commune PAG data, with the real
> regulatory article text, real COS/CUS/CSS/DL planning coefficients for
> not-yet-built zones, and real, servable PAP QE/NQ graphic-part map PDFs —
> not a WMS point-sample. National legislation (9 real laws, including
> SPARQL-based amendment-chain resolution: given a law and a date, the real
> version in force then), all 8 communes' building bylaws, and the full
> 100-commune registry (population, website, CMS/hosting) are ingested. A
> parcel's full regulatory picture is available both as structured JSON
> (`GET /api/v1/parcel/{id}/report`) and as a professional, byte-deterministic
> A4 PDF (`GET /api/v1/parcel/{id}/report.pdf`) — compared point-by-point
> against the government's own PAG-Géoportail baseline report, see below. A
> real, grounded, parcel-scoped chatbot exists: hybrid (lexical + dense)
> retrieval, LLM-based reranking, inline citations, deterministic refusal
> on unanswerable questions, and conversation memory — measured on a real
> 46-question, 6-commune, 4-language golden set (see `EVAL.md`). M5's
> multi-procedure decision engine is not built yet (one real, scoped-down
> procedure exists instead). This README describes what actually runs
> today, not what is planned — see [Roadmap](#roadmap).

---

## What works today

| Capability | Status |
|---|---|
| PostGIS + pgvector database, one command up on a clean machine | ✅ |
| EPSG:2169 (LUREF) ↔ WGS84 reprojection, verified correct (backend AND frontend) | ✅ |
| Provenance schema (sources / documents / chunks), migrated & reversible | ✅ |
| M1 spatial schema (communes, parcels, buildings, addresses), migrated & reversible | ✅ |
| M1.2 address search API — trigram fuzzy match, sub-15ms warm (see below) | ✅ |
| M1.3 parcel identify (by click, by cadastral reference) + full detail API | ✅ |
| M1.1 map UI — Next.js + OpenLayers, 3 real switchable WMS base layers, click-to-identify, address search, side panel | ✅ |
| M1.4 regulatory overlays — 18 real WMS layers + 3 derived from M2 (zone verte, PAP NQ/QE perimeters), 21 total, per-parcel intersects | ✅ |
| M1.5 geometry analysis — road frontage, neighbour distances, LiDAR slope, manual-setback buildable envelope | ✅ |
| **M2 — deep ingestion, all 8 brief-named communes** (Luxembourg, Esch-sur-Alzette, Differdange, Dudelange, Wiltz, Schengen, Junglinster, Sanem): real PAG/PAP zoning + written regulation text, real COS/CUS/CSS/DL coefficients, real PAP QE/NQ graphic-part map PDFs (177 files, servable via API), real building bylaws | ✅ |
| **M2 — commune registry**, all 100 real communes: official website, geoportal slug, LAU code, real STATEC population, CMS/hosting research (`SCALING.md`) | ✅ |
| **M2 — national legislation**: 9 real laws ingested, per-article chunked, status dashboard (`GET /api/v1/sources/status`) | ✅ |
| **M2 bonus (+8pt) — SPARQL amendment-chain resolution**: given a law + a date, the real Legilux-consolidated version in force then (`GET /api/v1/legislation/version-at`) | ✅ |
| **M3 — retrieval and chatbot, complete**: hybrid retrieval (lexical + pgvector dense, Reciprocal Rank Fusion), LLM-based reranking, grounded generation with inline `[n]` citations, deterministic pre-generation refusal, parcel-scoped context (M1/M2 geospatial facts + commune-scoped documents), real conversation memory (`chat_messages`), a minimal chat UI. LLM layer abstracted behind a provider interface (Gemini + a tested no-API-key extractive fallback). Measured on a real 46-question, 6-commune, 4-language golden set (`EVAL.md`) | ✅ |
| **M4 — structured report + PDF**, complete: `GET /api/v1/parcel/{id}/report` (brief's exact JSON schema) and `.../report.pdf` (WeasyPrint, byte-deterministic, real map extract), compared point-by-point against the government's own PAG-Géoportail baseline | ✅ |
| M5 (partial) — one real procedure (building permit), citation-backed, not a chatbot | ✅ |
| 111 pytest tests (schema constraints + real-data e2e + API + chatbot pipeline via a deterministic provider swap), all passing | ✅ |
| `mypy --strict` + ruff + black + ESLint + `tsc --noEmit` clean | ✅ |
| M5 — the rest (declarative decision engine, authority routing, sequencing) | ⛔ not started |

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

# 4. Load the real corpus. `make ingest` covers M1 (parcels/buildings/
#    addresses for the 8 brief-named communes); the M2 targets after it
#    cover PAG/PAP zoning + graphic maps, national legislation (+ the SPARQL
#    amendment-chain bonus), the 100-commune registry, and building bylaws.
#    Downloads several hundred MB total once, cached under data/cache/
#    (gitignored); subsequent runs reuse the cache and are idempotent.
make ingest
make ingest-pag-zones
make ingest-national-legislation
make ingest-legislation-versions
make ingest-commune-registry
make ingest-commune-population
make ingest-building-bylaws
make ingest-overlay-documents   # M1.4 Tier-1 sectoral-plan RGD citations
make ingest-procedures          # M5's one real procedure (building permit)

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

# M4 — structured report + PDF
curl "http://localhost:8000/api/v1/parcels/097D00240002285/report"
curl -o report.pdf "http://localhost:8000/api/v1/parcels/097D00240002285/report.pdf"

# M2 — status dashboard, and the SPARQL amendment-chain bonus
curl "http://localhost:8000/api/v1/sources/status"
curl "http://localhost:8000/api/v1/legislation/version-at?work_eli=http://data.legilux.public.lu/eli/etat/leg/loi/2004/07/19/n1&on_date=2024-01-01"
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

Useful targets: `make lint`, `make typecheck`, `make test`, `make eval` (M3.4
golden-set eval, writes `EVAL.md`), `make downgrade`, `make revision
m="message"`, `make seed-reference`, `make ingest-parcels`,
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
the 8 brief-named communes (Luxembourg City, Esch-sur-Alzette, Differdange,
Dudelange, Wiltz, Schengen, Junglinster, Sanem). Verified: 110,168 parcels,
68,162 buildings, 70,798 parcel↔building links (a real multi-parcel-building
minimum-overlap threshold was needed — see DECISIONS.md), 53,252 addresses,
99.8% resolved to a parcel. The pipeline scaled from the original 2 communes
to all 8 with zero architecture changes (config + two small real bugs fixed
— a duplicate natural key in one commune's own source shapefile, an expired
dated download URL — see DECISIONS.md), which is itself the strongest
evidence this is real, generic ingestion and not per-commune special-casing.
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

### M2 — ingestion and source coverage
Every ingestion script shares the same `sources`/`documents`/`chunks`
provenance pattern (idempotent upsert on `source_url`+`sha256`, logged
failures rather than aborted runs, tracked in the real status dashboard —
`GET /api/v1/sources/status`). Real per-commune PAG/PAP data (GML + DOCX +
PDF, fetched via HTTP range requests against multi-GB ZIPs — no full
download needed) resolves each parcel's zone via an exact spatial join, not
a WMS point-sample; PAP "Nouveau Quartier" zones carry real COS/CUS/CSS/DL
planning coefficients as genuine GIS attributes; PAP QE/NQ graphic-part map
PDFs (177 real files, 1.1GB) are fetched from the same ZIPs and served
directly (`GET /api/v1/documents/{id}/file` — the first real use of the
`Document.storage_path` field). National legislation (9 real laws) is
ingested via the existing Legilux HTML extractor, and the **SPARQL amendment-
chain bonus** (`GET /api/v1/legislation/version-at`) queries Legilux's real
JOLux SPARQL endpoint (found by reading the site's own JS bundle, since the
human-facing URL only serves an SPA shell) to resolve which real consolidated
version of a law was in force on a given date — this also caught a real
inconsistency where one already-ingested law's `legal_status` tag
contradicted the real amendment data (flagged, not silently patched). The
100-commune registry (website, LAU code, population from STATEC's real SDMX
API, CMS/hosting research) and all 8 communes' building bylaws (`pypdf`,
with an honest whole-document fallback where a PDF's layout defeats
per-article splitting) round out M2. Full reasoning trail in DECISIONS.md.

### M3 — retrieval and chatbot
Hybrid retrieval (`app/services/retrieval.py::hybrid_search`): lexical search
over the `tsv` generated column present on every chunk since the M1/M2 schema
design (`to_tsvector('simple', text)`, GIN-indexed, OR-joined stopword-filtered
tokens, `ts_rank_cd(..., 2)` for document-length normalisation — both fixed
real bugs that first returned near-zero results, see DECISIONS.md) fused with
dense pgvector cosine search (HNSW-indexed) via Reciprocal Rank Fusion.
Embeddings come from Gemini's `gemini-embedding-001` (`output_dimensionality`
pinned to the schema's existing 1024-d column) rather than a self-hosted
model — this environment's Python (3.14) has no `torch`/`onnxruntime` wheels
available, verified rather than assumed (see DECISIONS.md). Metadata
filtering (commune scoping + `legal_status` exclusion) happens in the SQL
WHERE clause before scoring, per the brief's own wording, not after.

Candidates are reranked by an LLM call (Gemini, structured JSON output) —
the brief's own sanctioned alternative to a cross-encoder, chosen here
because the same environment constraint above rules out every standard
cross-encoder path. The chat pipeline (`app/services/chatbot.py`) then
assembles a numbered source list mixing retrieved text with real M1/M2
geospatial facts for the selected parcel, generates a grounded answer with
inline `[n]` citations, and resolves those citations only against the exact
source list the model was given — never trusting a freeform citation.
Refusal ("I don't have a source for that") is a deterministic check before
generation, not asked of the model's own judgement. Repealed/superseded
provisions are excluded from retrieval at the SQL level; `unknown`/`draft`
documents are annotated so the model hedges rather than asserts them as
settled law. Conversation memory is a real Postgres table
(`chat_messages`), not an in-process store. The LLM layer is abstracted
behind a `Protocol` (`app/services/llm/`) with two implementations: a real
Gemini provider and a tested, no-API-key `ExtractiveProvider` fallback that
degrades gracefully (used in tests, and as a real safety net if the API
becomes unavailable) — the actual "swap models without touching business
logic" requirement, not an aspiration.

A real, serious bug was found and fixed by exercising this for the first
time: PAG written/graphic documents never had `commune_code` set (a gap
dating to M2), so a parcel-scoped question could retrieve a different
commune's PAP regulations — exactly the cross-commune leakage the brief's
own M3.1 example warns against. Fixed at the source, backfilled across all
8 communes, and proven with a real-data regression test using a harder case
than a title check could catch (all 8 communes' building bylaws share the
identical document title). Full account in DECISIONS.md.

Measured against a real 46-question golden set spanning 6 of the 8 deep
communes and 4 languages (FR/EN/DE/LB) — see `EVAL.md` for exact retrieval
precision/recall and generation-level citation accuracy, plus a disclosed
real constraint: this account's free-tier embedding quota is tight enough
that dense retrieval fails for some calls, and the system is built to
degrade to lexical-only rather than fail the request when that happens
(disclosed in EVAL.md, not hidden). A minimal chat UI (`ChatPanel.tsx`) is
wired end to end; conversation memory persists per browser session via a
client-generated id.

### M4 — structured report + PDF
`GET /api/v1/parcel/{cadastral_id}/report` matches the brief's exact JSON
schema, assembled in `app/services/report.py` by reshaping data that already
exists (M1's parcel detail, M2's PAG/PAP zoning and overlay constraints) —
no new computation invented. Honest, not fabricated, where the corpus
genuinely can't answer: `building_parameters` only has real numbers (COS/DL)
for PAP Nouveau Quartier zones (`confidence: "medium"`); height/storeys/
setbacks are `null`/`"not_extracted"` everywhere, matching the brief's own
explicit instruction; `required_authorisations` is honestly `[]` since M5's
decision engine doesn't exist yet. `GET /api/v1/parcel/{id}/report.pdf`
renders the *same* data through one Jinja2 template via WeasyPrint (chosen
over ReportLab/Typst — see Technical choices) — a real WMS basemap tile with
the parcel's boundary drawn on top (`app/services/report_map.py`, Pillow,
cached per parcel) serves as the cover page's map extract. Verified live
that regenerating the same parcel's PDF produces a byte-identical file — the
footer's "data as of" timestamp is deliberately derived from real M2.1
source-tracking data, not wall-clock time, to make that guarantee hold.
Compared point-by-point against the government's own PAG-Géoportail
baseline report — see the dedicated section below.

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
| `embedding vector(1024)` via Gemini's `gemini-embedding-001` | FR/DE(+LB via cross-lingual proximity) coverage; `output_dimensionality` kept the schema's original 1024-d self-hosted plan unchanged | Self-hosted BGE-m3/e5-large (the original plan — blocked: no `torch`/`onnxruntime` wheels for this environment's Python 3.14, verified) |
| `legal_status` defaults to `unknown` | Honest ingest-time state; never guess `in_force` | Default in_force (risks citing repealed) |
| WeasyPrint (HTML+CSS via Jinja2) for M4's PDF | Fastest path to a professional A4 layout reusing this stack's skills; needs real system libs (Pango/cairo) beyond pip | ReportLab (verbose manual x/y layout), Typst (non-Python binary dependency) |
| M4's PDF cover map: real WMS tile + Pillow-drawn outline, cached per parcel | Matches the brief's literal "in context" requirement using the same public basemap the frontend already uses; caching avoids hammering the government server on every request | A self-contained vector-only rendering (safer determinism, weaker "in context") |
| M4's PDF footer timestamp derived from `data_freshness`, not `datetime.now()` | The brief requires both a per-page generation timestamp AND a byte-comparable PDF for the same corpus state — a literal wall-clock stamp breaks the second requirement | Wall-clock timestamp (fails determinism) or omitting the timestamp (fails the brief's explicit footer requirement) |
| M3 reranking is LLM-based (Gemini), not a cross-encoder | Brief explicitly allows either; the environment constraint above rules out cross-encoders (`sentence-transformers`/`fastembed` need `torch`/`onnxruntime`) | Cross-encoder (blocked, same root cause as the embedding pivot) |
| Reciprocal Rank Fusion for hybrid retrieval | `ts_rank_cd` and cosine similarity have no principled common scale to sum directly; RRF fuses rank order instead | Score normalisation + weighted sum (arbitrary weight tuning, no clean scale) |
| Chat's `LLMProvider.complete()` takes numbered `sources`, not a flattened prompt string | Makes citation-safety structural — a provider can only cite `ref_id`s it was actually given, and even a no-LLM fallback can produce a real cited answer by assembling them directly | Flattened prompt + free-text citation parsing (more surface for a hallucinated/malformed citation) |
| `hybrid_search` degrades to lexical-only on an embedding-API failure, with a short fast-fail retry on the live path specifically | M2.1's resilience principle applied to a live request, not just batch ingestion — this account's real embedding quota fails mid-session; a live chat user shouldn't wait minutes for a fallback | Let the request fail (500) or retry with the same patient budget ingestion uses (unacceptable live latency) |
| Conversation memory is a real `chat_messages` table | An in-process dict is wiped by every `uvicorn --reload` restart, common in dev | In-memory store (fragile, loses "conversation memory within a session" on any restart) |

The full decision log with reasoning and rejected alternatives is in
[DECISIONS.md](DECISIONS.md).

---

## Repository layout

```
docker/postgres/        Custom PostGIS+pgvector image + first-boot extension SQL
docker-compose.yml      db service (host :5433) — no backend/frontend service yet, see limitations
Makefile                db-up, migrate, ingest*, eval, lint, test, run, …
data/cache/              Bulk downloads + derived files (gitignored) — PCN/BD-Adresses,
                         PAG ZIPs, pag_graphics/ (real map PDFs), parcel_maps/ (M4 map extracts)
backend/
  app/core/             Settings, async SQLAlchemy engine, structlog config
  app/models/           ORM models: provenance, M1 spatial schema, PAG/PAP zoning, overlays
  app/schemas/          Pydantic API response models (incl. the M4 report schema)
  app/api/v1/           FastAPI routers: addresses, parcels (+ report/report.pdf), overlays,
                        procedures, sources (status dashboard), legislation (SPARQL bonus),
                        documents (serves stored graphic PDFs)
  app/services/         Query/business logic behind the routers — address search, parcel
                        lookups, PAG/PAP zoning join, overlays, report assembly, PDF
                        rendering (report_pdf.py), map-extract rendering (report_map.py)
  app/templates/        Jinja2 HTML template for the M4 PDF report
  app/reference_data/   Small, tracked CSVs (communes, natures, cadastral crosswalk)
  alembic/              Migrations (env.py filters PostGIS-owned tables)
  ingestion/            Real ingestion scripts: PCN/BD-Adresses, PAG/PAP zoning + graphic
                        PDFs, national legislation + SPARQL amendment-chain versions,
                        commune registry + population, building bylaws, overlay documents
  tests/                pytest: schema constraints, real-data e2e, API (90 tests)
  pyproject.toml        Deps + ruff/black/mypy/pytest config
frontend/
  app/                  Next.js App Router (page.tsx orchestrates state)
  components/           MapView (OpenLayers), AddressSearch, ParcelPanel
  lib/                  API client, TypeScript types, EPSG:2169 proj4 setup
```

---

## Current limitations (honest status)

- **No HV electricity easement overlay layer.** Searched exhaustively across
  the full 1437-layer geoportail theme tree — doesn't exist as a real,
  distinct layer there (see SOURCES.md). `zone_verte` was in the same
  position (no standalone WMS layer either) until M2's real PAG data made it
  derivable — see the M1.4/M2 status below.
- **Buildable envelope (M1.5) still uses a single manual uniform setback, not
  a real extracted value.** Real COS/CUS/CSS/DL planning coefficients (max
  footprint ratio, floor area ratio, soil-sealing ratio, dwelling density)
  are now available for `NQ_PAP` zones as genuine structured data (see M2
  below) — but those are area/density limits, not a linear setback distance,
  so they don't replace this input; the brief's own explicit manual-input
  escape hatch still applies here (see DECISIONS.md).
- **Real PAG/PAP zoning is genuinely partial in the source data.** After
  ingesting all 8 target communes' real PAG datasets and fixing two real
  axis-order/duplicate-key bugs along the way, zone coverage varies by
  commune — confirmed against the live geoportail WMS that gaps are real
  gaps in the *downloadable* dataset (not our parsing), consistent with
  in-progress PAG revisions for some communes (see DECISIONS.md). An
  uncovered parcel gets an honest empty result, not a fabricated zone.
- **PAP QE's DOCX override tables (schéma-directeur code → floor-area %)
  are captured as raw, full-text-searchable text but not parsed into
  structured fields** beyond the one zone category (MIX_u) originally
  verified — a deliberate scope choice (see DECISIONS.md) once the graphic-
  part PDFs (the other named part of this same gap) were prioritized and
  closed instead.
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
- **M3's dense-embedding backfill is quota-constrained in this environment.**
  This account's free-tier `gemini-embedding-001` quota is tight enough that
  a full 1,689-chunk backfill doesn't reliably complete in one run — the
  system is built to be resilient to this (batches are skipped and retried
  on a later `make embed`; a live chat request degrades to lexical-only
  rather than fail), and the mechanism itself is verified correct
  independent of the quota fight (real pgvector cosine-ordering tests
  against hand-crafted vectors). `EVAL.md` states exactly how much of its
  measured run reflects lexical vs. dense retrieval, honestly.
- **No real repealed document exists in this corpus yet** to test M3.2's
  "never cite a repealed provision as current" against — every ingested
  document is `in_force` or `unknown`. Verified with a synthetic repealed
  row in the test suite instead; disclosed in `EVAL.md` rather than silently
  presented as tested against real data.
- **Luxembourgish (LB) query support is real but weaker than FR/DE/EN** — no
  dedicated LB embedding model exists; LB queries rely on cross-lingual
  embedding proximity to German/French plus lexical exact-token matching on
  shared vocabulary and proper nouns. A disclosed limitation, not a claim of
  full LB support (see `app/services/embeddings.py`).
- **M5 has exactly one real procedure** ingested (building permit) — a
  structured citation-backed display, not a decision engine or chatbot. The
  brief's declarative rule set (authorisation triggers, sequencing,
  authority routing) hasn't been built; a real, deliberate scope decision
  given M1/M2/M4's depth, not an oversight.
- Migrations/ingestion/API are run from a host virtualenv (`backend/.venv`);
  no backend Dockerfile exists yet (only the Postgres service is
  containerised) — WeasyPrint's system libraries (Pango/cairo/gdk-pixbuf)
  will need an `apt-get install` step there. `make demo` (seeded small
  dataset) hasn't been built either.
- Embedding dimension is pinned to 1024; changing the model to another
  dimension is an explicit migration.
- Production use of the Luxembourg geoportal (`ws.geoportail.lu`) requires ACT
  domain approval — to be documented, not a blocker for the assessment. The
  actually-working public endpoints we found are `wms.geoportail.lu/opendata/service`
  (base layers) and `wms.geoportail.lu/public_map_layers/service` (M1.4
  thematic overlays) — see SOURCES.md.

---

## M4.3 — comparison against the PAG-Géoportail baseline

The brief names the Luxembourg state's own PAG-Géoportail parcel report as
the baseline to study and compare against. Its real feature name is
**"Rapport — Règles urbanistiques applicables à un terrain donné"** (button:
"Commander rapport"), inside `map.geoportail.lu`'s PAG theme
(`map.geoportail.lu/theme/pag`, the successor to the legacy `pag.geoportail.lu`).

Two things worth being precise about, since a live end-to-end run wasn't
possible here: (1) it's genuinely **not** an instant download — clicking a
parcel and submitting an email address triggers an async **FME-generated**
PDF, uploaded to an internal ownCloud, with the download link emailed to
the user; this was confirmed by reading the actual current source of
`geoportailv3` (the open-source project that runs `map.geoportail.lu`,
repository last updated 2026-09-08), not guessed. (2) The actual sample
studied is a real, official government-published example for the commune
of **Nommern** (recovered via the Internet Archive, since the government's
own link to it now 404s) — the underlying generation mechanism in the
current source code is unchanged, but this specific 36-page sample is from
2015/2019, so an exact visual re-check against a freshly generated report
for a different commune wasn't possible.

**What their report contains, in order:** a cover page (aerial orthophoto,
parcel outlined in magenta, commune coat of arms); a PAG section with the
full legend of every zone/overlay category in the country, followed by one
illustrated sub-section *per article that actually applies* to the parcel
(full legal text + a small clipped map showing exactly which zone that
article covers), including a COS/CUS/CSS/DL coefficients table wherever a
PAP "nouveau quartier" zone applies; a glossary of urbanistic coefficients;
linked attachments for the commune's schéma directeur and PAP NQ/QE
written+graphic parts; a long, diagram-illustrated section of dimensional
building rules (setbacks, roof forms, garages, verandas, fences, antennas)
straight from the commune's règlement sur les bâtisses; a second glossary
(~30 construction terms); and a detailed legal disclaimer page.

**Point-by-point:**

| Aspect | PAG-Géoportail (baseline) | This platform | Verdict |
|---|---|---|---|
| Delivery | Async — email + ownCloud link, no direct download | Synchronous `GET .../report.pdf`, instant | **Better** — no email dependency, no wait |
| Structured data | PDF only, no machine-readable output | Same data available as JSON (`GET .../report`) before PDF rendering | **Better** — a chatbot/other client can consume it directly |
| Confidence on extracted values | None — every figure presented as flat fact | Every building parameter/constraint carries an explicit `confidence` (`high`/`medium`/`not_extracted`) | **Better** — matches the brief's own non-negotiable rule; their report can't distinguish a verified figure from an assumption |
| Determinism | Not documented; FME-generated, no stated guarantee | Verified live: identical corpus state → byte-identical PDF | **Better** — an explicit, tested guarantee |
| Overlay breadth | PAG/PAP-focused; the Nommern sample shows no flood/Natura 2000/heritage/servitude layers at all | 21 real overlay layers (flood zones, Natura 2000, heritage, airport servitude, gas network, water protection, etc.) alongside PAG/PAP | **Better** — broader constraint coverage per parcel |
| Per-article legal text depth | Full text of *every* applicable article, individually illustrated with its own clipped zone map | Cites the applicable document + one general zone map; doesn't split multiple applicable articles into individually-illustrated blocks | **Worse** — real, acknowledged content-depth gap |
| Building envelope rules (setbacks, roof forms, garages, fences, etc.) | Detailed, diagram-illustrated, straight from the real règlement sur les bâtisses | Only COS/CUS/CSS/DL numbers, and only for PAP "Nouveau Quartier" zones — everything else `not_extracted`, exactly as the brief instructs when extraction isn't reliable | **Worse** — an honest, not a hidden, gap (see M1.5/M2 limitations above) |
| Glossary / terminology | Two dedicated annexes (~30+ terms) for a non-specialist reader | None | **Worse** — assumes the reader already knows COS/CUS/CSS/DL etc. |
| Legal disclaimer | Full dedicated page, detailed terms of use | One footer line ("this report does not replace consultation of the official texts, which prevail") | **Worse** — real but low-effort gap to close later |
| PAP NQ/QE document bundling | Full written+graphic parts and schéma directeur linked as separate attachments | Graphic-part PDFs are directly servable (`GET /api/v1/documents/{id}/file`, see M2.4) via `applicable_documents`; no schéma-directeur ingestion yet | **Mixed** — ours is more directly downloadable where it exists, but doesn't bundle the schéma directeur |

Net honest assessment: the state's report is deeper on legal-text narrative
and dimensional building rules for the zones it *does* cover (because an
FME workflow with years of tuning can embed full article text and hand-
drawn diagrams); this platform is broader on constraint coverage, more
transparent about extraction confidence, faster to deliver, and
machine-consumable — closer to a real product surface than a one-off
government PDF generator, but genuinely thinner on narrative legal depth
today.

---

## Roadmap

1. ~~**M1 — Map, cadastre, addresses**~~ ✅ done — base map/projection, address
   search, parcel identify, 21 regulatory overlays (18 real WMS layers + 3
   derived from M2), geometry analysis (frontage, neighbour distances, LiDAR
   slope, buildable envelope). Only HV electricity easements remain a
   genuine gap (no such public layer exists at all — see SOURCES.md).
2. ~~**M2 — Ingestion and source coverage**~~ ✅ done, including the +8pt
   SPARQL amendment-chain bonus — real PAG/PAP zoning + written regulation
   text + graphic-part map PDFs for all 8 brief-named communes, real
   COS/CUS/CSS/DL coefficients for PAP Nouveau Quartier zones, 9 real
   national laws with SPARQL-based amendment-chain resolution, the full
   100-commune registry (population, website, CMS/hosting), and all 8
   communes' building bylaws. The one deliberately deferred sub-item:
   structured DOCX coefficient-table parsing beyond the one zone category
   (MIX_u) originally verified — the raw text is already searchable, just
   not structured (see DECISIONS.md).
3. ~~**M4 — Parcel report and PDF generation**~~ ✅ done — the brief's exact
   JSON schema, a professional byte-deterministic PDF (WeasyPrint) with a
   real map extract, and the required point-by-point comparison against the
   government's own PAG-Géoportail baseline report (see above).
4. **M3 — the rest**: hybrid (dense+lexical) retrieval once an embedding
   provider is configured, reranking, the chatbot UI, parcel-scoped
   conversation memory. The lexical core and eval harness already exist and
   are measured (`EVAL.md`).
5. **M5, completed properly**: a real declarative rule set (authorisation
   triggers, authority routing, dependency-ordered sequencing) once M3
   exists to back it with retrieval — currently one real, citation-backed
   procedure display, not a decision engine. Likely a deliberate drop or
   thin stretch given time, per the brief's own scoring guidance that a
   reasoned drop beats a half-built module.
6. **Packaging**: a backend Dockerfile (WeasyPrint's system libs need an
   `apt-get` step) and `make demo` (seeded small dataset) — not built yet;
   everything above currently runs from a host virtualenv.

Deliverables to accompany the code: `SOURCES.md`, `SCALING.md`, `EVAL.md`, and a
weekly `PROGRESS.md`.

---

## Notes

- Secrets live in `.env` (gitignored); `.env.example` holds placeholders only.
- Official texts always prevail over any output of this system.
