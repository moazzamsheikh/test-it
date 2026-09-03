# Progress

## 2026-09-01 — M1 foundation, M1.1-M1.5 working end-to-end

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

**M1.4 — Regulatory overlays:** 18 real thematic WMS layers (PAG zoning, Natura 2000, flood zones, servitudes, gas network, etc.) found by reading the official geoportail client's own theme config, not guessed. Per-parcel intersects computed via point-sampled GetFeatureInfo and cached (`parcel_overlay_results`) — first view ~10s, every view after ~25ms. Frontend: independent overlay checkboxes + a constraints panel (amber cards for what applies).

**M1.5 — Geometry analysis** (stretch, per the brief itself): road frontage onto real road-nature parcels (no external road dataset needed — ACT's own PCN data already tags ~1,915 parcels as roads), nearest-neighbour distances (min boundary-to-boundary, capped/radius-bounded), slope from a real open (CC0) 2024 LiDAR terrain model via windowed COG range-reads (no full 40GB download), and a manual-setback buildable envelope (PAG/PAP setback values aren't extractable yet — M2 hasn't started — so this is the brief's own explicit manual-input escape hatch, not a guess). All four verified live against real parcels, cached where the source is external/slow (slope).

**Quality bar:** 32 automated tests (schema constraints + real-data end-to-end + API), all passing. `mypy --strict` / ruff / black / ESLint / `tsc --strict` all clean. Verified in an actual headless browser (Playwright), not just linters.

**A serious bug caught by a user report, not by testing:** the map rendered a real address ("8 Rue Beck") ~15km from its true location. Investigation traced it to WMS 1.3.0 + EPSG:2169's registered axis order (Northing,Easting, confirmed against the EPSG registry) being silently mishandled — affecting not just map rendering but every M1.4 regulatory-overlay computation, since the same bug was in the backend's GetFeatureInfo point-sampling. Fixed by downgrading to WMS 1.1.1; the entire overlay cache was purged and recomputed. Full writeup in DECISIONS.md and WALKTHROUGH.md — flagged prominently because it's the most consequential bug found in the project so far, and because catching it required following a visual bug report to a backend correctness issue the user never mentioned.

### Two real bugs worth mentioning (both caught by testing, not code review)
- A guessed coordinate-reprojection parameter looked entirely reasonable and was **108 metres wrong** — would have silently misidentified parcels on every map click. Caught by checking it against the backend's own verified transform before writing any UI code.
- A missing database index meant address search was doing a full table scan (110ms) despite the design doc saying otherwise — a decision that was written down but never actually implemented. Caught by running `EXPLAIN ANALYZE`, not by reading the code.

Both are fixed, and both are logged in `DECISIONS.md` along with ~30 other decisions and the reasoning behind them.

### Known gaps (deliberate, not hidden)
- No declared/legal parcel area source found yet in PCN — reported honestly as "not extracted" rather than guessed.
- Address search doesn't yet cover full FR/DE/LB street-name aliasing (only common abbreviations) — real alias data exists (CACLR) but isn't ingested yet.
- No `zone_verte` or HV electricity easement overlay layer — searched exhaustively across the full 1437-layer geoportail theme tree, neither exists there as a real layer.
- Buildable envelope uses one manual uniform setback, not real PAG/PAP values (M2 hasn't ingested legislation yet).
- M2-M5 (legislation ingestion, chatbot, PDF report, procedure assistant) not started.

## 2026-09-02 — WMS axis-order bug fixed; M5 partial (one real procedure)

**Bug fix:** see the entry above (moved here would duplicate it — same day's work). Root cause, fix, and blast radius are fully written up in DECISIONS.md/WALKTHROUGH.md.

**M5 — Procedure (partial, out of roadmap order at explicit request):** no spec text exists anywhere in this project for M5, unlike M1.4/M1.5 where the brief's exact wording was pasted before starting — flagged that honestly, and the user chose to proceed on a reasonable interpretation rather than provide it, on the condition it avoid the M2/M3 dependency. Built: a structured, citation-backed display of exactly ONE real government procedure — guichet.public.lu's real building-permit page (found via web search), ingested through the `sources`/`documents`/`chunks` schema that already existed from the M1 foundation (no new tables). Real content only: every section's text, the €6,197.34 exemption threshold, the 2-year validity period, and all 5 legal-basis citations (real Legilux ELI URLs) are the government's own verbatim French text, extracted via BeautifulSoup, not paraphrased. Explicitly labelled in the UI as "not a chatbot, and not specific to this parcel" — a real multi-procedure, retrieval-backed assistant needs M3 first. 4 new tests (extraction against a saved real-page fixture + a service-level read of the real ingested row), all passing; 36 total.

## Plan for the rest of the assessment

1. **M2 — Ingestion & provenance**, the highest-weighted module: national legislation via the Legilux SPARQL endpoint (in-force versions only), the two communes' PAG/PAP/building bylaws, idempotent pipeline, status dashboard, the 102-commune scaling analysis.
2. **M4 — Report + PDF**, then **M3 — hybrid retrieval + chatbot + eval harness**, in that order, since M4 depends less on M3 being solid first.
3. **M5, completed properly**: a real multi-procedure, retrieval-backed assistant once M3 exists — likely dropped deliberately given time, unless M1-M4 land comfortably early.

The vision hasn't changed: fewer modules built to a real, defensible standard beats five built shallowly. Everything above is chosen so each module either directly unblocks the next one, or stands alone as a genuinely working, testable piece if time runs out before the rest.
