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

**M2 — PAG/PAP zoning (partial), from a real requirement dictated via video, not the assessment PDF:** the user shared three screen-recording transcripts demonstrating a real Luxembourg zoning-lookup workflow (PAG written + graphic parts, PAP "Quartier Existant" sub-variants, per-commune sourcing). Captured in a new `PAG_PAP_SPEC.md` before writing any code. Researched (not assumed) that both target communes — Wiltz and Luxembourg City — publish real, open (CC0) per-commune PAG datasets on data.public.lu (GML + DOCX/PDF). Key finding: resolving "which regulation applies to this parcel" is a real point-in-polygon spatial join against real `ZONAGE`/`ZONES_QE` polygons that carry the exact document filename as a GIS attribute — a cleaner, more reliable mechanism than the video's manual leader-line navigation. Built: `pag_zones`/`pap_qe_zones` tables, a real ingestion pipeline (`make ingest-pag-zones`) reading individual entries out of large (1.95GB/406MB) remote ZIPs via HTTP range requests rather than downloading them whole, and a spatial-join service wired into the parcel detail API and side panel. Verified live: "8 Rue Beck" resolves to a real (if surprising) `FOR` zone classification with the real Art.19 legal text.

Two real problems found and fixed during implementation: (1) a second, independent axis-order bug — this time inside ACT's own downloadable GML for Wiltz specifically, opposite to Luxembourg City's — caught by 0% parcel overlap and fixed with an empirical per-commune check against real ingested parcels, not a hardcoded exception; (2) a genuine, partial data-completeness gap in the source datasets themselves (65.0%/53.8% real parcel coverage), confirmed via the live government WMS to be real and not a parsing bug, reported honestly rather than hidden. 4 new tests (real-parcel resolution, real-parcel-with-a-real-gap, 2 hermetic axis-swap tests using real geometry), all passing; 40 total.

**M2 — real COS/CUS/CSS/DL planning coefficients**, prompted by a direct follow-up question ("retrieve the information for CUS, COS, CSS, DL for a given PAP NQ"). Checked before assuming anything: these numbers turned out to be genuine, populated GIS attributes on `NQ_PAP` ("Nouveau Quartier" — not-yet-built zones), not something requiring the document-table parsing planned for PAP QE's coefficients. Verified live for both communes — e.g. a real Weimershof zone: COS≤0.6, CUS≤1.25, CSS≤0.8, DL≤115, matching the original video's example numbers almost exactly. New `pap_nq_zones` table, ingested and spatially joined the same way as the existing PAG/PAP tables; the zone's shared written regulation is ingested and cited, the per-project schéma-directeur PDF is a filename reference only (same deliberate scope limit as PAP QE's graphic parts). Caught and fixed a real bug during live verification (not by inspection): a parcel spanning multiple disjoint same-category zone fragments produced duplicate React keys — fixed by keying on index. 1 new test, 41 total.

**M1.4 audit against the assessment's own scored spec text**, at the user's request. Went line-by-line against the actual brief (not memory/summary) and found two of M1.4's explicitly-named overlay categories — "zone verte" and "PAP NQ / PAP QE perimeters" — weren't actually answerable, despite 18 other real layers being wired up. Both turned out to be cheaply closable with M2 data already ingested: the real PAG legend groups four already-ingested `ZONAGE` categories (`AGR`/`FOR`/`PARC`/`VERD`) under a "Zone verte" heading, and M2's `ZONES_QE`/`NQ_PAP` polygon data directly answers the perimeter question (distinct from the narrower `pap_approuves` WMS layer, which only covers individually-approved PAP projects). Implemented as derived `OverlayConstraint` entries appended to the existing constraints list — zero frontend changes needed, since that UI already renders any constraint generically (verified live: "21 apply" instead of 18, zero console errors). HV electricity easements remain the one genuine, permanent gap: confirmed no such layer exists on this public service at all. 3 new tests, 44 total. Also surfaced two other real, permanent gaps while auditing: CACLR alias data for full FR/DE/LB address search isn't ingested (BD-Adresses only), and the M1.3 "area compared to declared area" bullet is honestly `null` since PCN carries no declared-area field at all.

## Plan for the rest of the assessment

1. **M2 — the rest**, still the highest-weighted module: national legislation via the Legilux SPARQL endpoint (in-force versions only), building bylaws, the status dashboard, the 102-commune scaling analysis. PAG/PAP zoning for both target communes is now real and working (see above) — two honest gaps remain: coefficient tables aren't parsed into structured fields, and PAP QE's graphic-part PDFs aren't ingested.
2. **M4 — Report + PDF**, then **M3 — hybrid retrieval + chatbot + eval harness**, in that order, since M4 depends less on M3 being solid first.
3. **M5, completed properly**: a real multi-procedure, retrieval-backed assistant once M3 exists — likely dropped deliberately given time, unless M1-M4 land comfortably early.

The vision hasn't changed: fewer modules built to a real, defensible standard beats five built shallowly. Everything above is chosen so each module either directly unblocks the next one, or stands alone as a genuinely working, testable piece if time runs out before the rest.
