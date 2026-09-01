# Progress

## 2026-09-01 — M1 foundation, M1.1-M1.3 working end-to-end

### What's done

**Foundation (verified, not just built):**
- PostgreSQL 16 + PostGIS + pgvector, custom Docker image, one-command up.
- Provenance schema (`sources`/`documents`/`chunks`) for M2/M3 — migrated, reversible.
- M1 spatial schema: communes, parcels, buildings, addresses, reference tables — 9 tables, 4 migrations, all reversible.

**Real data, not fixtures:**
- Ingested actual PCN (cadastre) + BD-Adresses for the two contrasting communes (Wiltz, Luxembourg City): **40,291 parcels, 28,891 buildings, 29,831 parcel↔building links, 23,680 addresses (99.8% resolved to a parcel)**.
- Pipeline is idempotent (`make ingest`) — verified by re-running and diffing row counts, not assumed.

**M1.2 — Address search:** live API, trigram fuzzy match + abbreviation handling + house-number parsing. **12.6ms warm** (`EXPLAIN ANALYZE`, real query).

**M1.3 — Parcel identify:** click-to-identify, cadastral-reference search, full detail (addresses, buildings, geometry). Identify returns a *list* — a boundary click can legitimately match >1 parcel, and that's surfaced honestly rather than guessed.

**M1.1 — Map UI:** Next.js + OpenLayers, working projection is EPSG:2169 (LUREF) itself — matching the official geoportail, not Web Mercator. Three real switchable WMS layers (Basemap, Orthophoto, Cadastral plan). Wired to M1.2/M1.3.

**Quality bar:** 21 automated tests (schema constraints + real-data end-to-end + API), all passing. `mypy --strict` / ruff / black / ESLint / `tsc --strict` all clean. Verified in an actual headless browser (Playwright), not just linters.

### Two real bugs worth mentioning (both caught by testing, not code review)
- A guessed coordinate-reprojection parameter looked entirely reasonable and was **108 metres wrong** — would have silently misidentified parcels on every map click. Caught by checking it against the backend's own verified transform before writing any UI code.
- A missing database index meant address search was doing a full table scan (110ms) despite the design doc saying otherwise — a decision that was written down but never actually implemented. Caught by running `EXPLAIN ANALYZE`, not by reading the code.

Both are fixed, and both are logged in `DECISIONS.md` along with ~30 other decisions and the reasoning behind them.

### Known gaps (deliberate, not hidden)
- No declared/legal parcel area source found yet in PCN — reported honestly as "not extracted" rather than guessed.
- Address search doesn't yet cover full FR/DE/LB street-name aliasing (only common abbreviations) — real alias data exists (CACLR) but isn't ingested yet.
- No regulatory overlays (M1.4) or geometry analysis (M1.5) yet.
- M2-M5 (legislation ingestion, chatbot, PDF report, procedure assistant) not started.

## Plan for the rest of the assessment

1. **M1.4 — Regulatory overlays.** Enumerate real thematic WMS/WFS layer names (PAG zoning, Natura 2000, flood zones, etc. — not done yet) and wire a generic, config-driven overlay mechanism, ≥10 real layers.
2. **M1.5 — geometry analysis** (frontage, slope, buildable envelope) as time allows — the brief itself frames this as a stretch goal within M1, not a hard requirement.
3. **M2 — Ingestion & provenance**, the highest-weighted module: national legislation via the Legilux SPARQL endpoint (in-force versions only), the two communes' PAG/PAP/building bylaws, idempotent pipeline, status dashboard, the 102-commune scaling analysis.
4. **M4 — Report + PDF**, then **M3 — hybrid retrieval + chatbot + eval harness**, in that order, since M4 depends less on M3 being solid first.
5. **M5 — procedure assistant**: likely dropped deliberately given time, unless M1-M4 land comfortably early. Flagging this now rather than discovering it in week 3.

The vision hasn't changed: fewer modules built to a real, defensible standard beats five built shallowly. Everything above is chosen so each module either directly unblocks the next one, or stands alone as a genuinely working, testable piece if time runs out before the rest.
