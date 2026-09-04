# PAG/PAP retrieval — requirements

## The core idea

Given a parcel, the platform should be able to resolve its zone code (e.g. `MixU`) and use
that as a retrieval key to serve the **exact** regulatory text and map excerpt that applies
— not a general summary, not the whole document, the specific section. Stated goal: *"if
anybody asks us, we can directly give this paper."*

**Explicit scope boundary (video 3):** the frontend should NOT try to replicate the full
layered zone-drawing complexity that geoportail.lu's own PAG viewer shows (all the
individual zone-boundary lines, sub-parcels, etc.). We only need the simple fact — *"this
parcel is in zone MixU"* — and that fact drives retrieval. The map is a lookup key, not
the deliverable.

---

## PAG — Plan d'Aménagement Général (commune-wide zoning)

1. **Zone resolution**: click/select a parcel → resolve its PAG zone code (e.g. `MixU`,
   `Hab-1`, `Hab-2`, `Gard`, `Parc`, etc. — the same taxonomy already confirmed real via
   the M1.4 WMS legend, see DECISIONS.md).
2. **Written part** (*partie écrite*): each commune publishes its own PAG regulation as a
   PDF on its own municipal website, under something like Urbanisme → *Plan d'Aménagement
   Général* → *Partie écrite*. The section covering the parcel's zone code is what
   retrieval must return — confirmed to sometimes span multiple pages.
3. **Graphic part** (*partie graphique*): the actual zoning map (PDF or image), showing
   the parcel's location within its zone. Retrieval must be able to serve/cite this
   alongside the written text — described as equally required, not optional.
4. **Built vs. not-built matters**:
   - Already built → typically renovation-relevant only, the written zone text is enough.
   - Not built (buildable) → additional **numeric coefficients** apply (examples given:
     `0.3`, `0.5`, `0.6`, `20`) — used to calculate buildable m², ground-floor footprint,
     and number of dwelling units. These are standard Luxembourg PAG concepts (COS/CUS/
     density-type coefficients) but the *exact* field names/meanings need verifying
     against a real Wiltz or Luxembourg City PAG document — not assumed from the demo.
5. **Coefficients are graphically anchored, not just zone-uniform**: on the graphic plan,
   numeric coefficients appear in annotation boxes connected to specific areas via a
   leader line — so two parcels in the same zone code can have *different* applicable
   numbers depending on which annotated area they actually fall under. Resolving the
   correct numbers for a given parcel requires matching its location against these
   graphic annotations, not just a zone-code lookup table. **This is a real, nontrivial
   geospatial sub-problem, not a simple join** — flagged honestly, not hand-waved.

---

## PAP — Plan d'Aménagement Particulier (finer-grained, per-quarter)

1. **QE vs NQ split**: *Quartier Existant* (already built) vs *Nouveau Quartier* (not
   built) are two distinct regulatory tracks with separate documents.
2. **Zone sub-variants**: within PAP QE, a PAG zone code like `MixU` further subdivides
   into sub-variants (e.g. `MixU`, `MixU-D`, `MixU-E`, `MixU-S`) — each with different
   rules. Determining *which* sub-variant applies to a specific parcel needs its own
   disambiguation step (via the PAP's own graphic map, cross-referencing a numbered
   annotation, e.g. "E → ref. 10" in the demo) — same graphic-annotation-matching
   pattern as PAG's coefficients, not a simpler lookup.
3. **Text spans real page ranges**: the demo's example needed pages 19-24 of one
   document for one zone sub-variant — retrieval chunking needs to handle this
   without artificially truncating a legally-complete section.
4. **Own graphic part**: PAP has its own separate map (named per locality within the
   commune in the demo, e.g. "Mersch-Réconge") used to confirm the exact sub-variant.

---

## Architectural implication: per-commune sourcing

PAG/PAP source documents are **not centralized** — each commune publishes its own on its
own website (confirmed directly: Mersch's documents live on Mersch's site, Lintgen's on
Lintgen's site, same document *type* and *structure*, different content). geoportail.lu's
"Gemeinden" (communes) boundary layer is how you determine *which* commune's site a given
parcel's documents live on. This directly matches — and now concretely justifies — the
102-commune scaling analysis planned for `SCALING.md` (not yet written): handling this
across every Luxembourg commune eventually; for this assessment, scoped to the two
communes already ingested (Wiltz, Luxembourg City).

---

## VERIFIED (2026-09-03): the real architecture is much cleaner than the demo's manual workflow

Researched directly — not assumed — by peeking inside the real datasets via HTTP range
requests (no need to download the multi-GB files in full; both are plain ZIPs, `compress_
type=0`/stored, so Python's `zipfile` + a range-request file-like object lists/reads
individual entries on demand). **This resolves the "nontrivial graphic-annotation-matching"
concern above as no longer a real problem for PAG/PAP QE** — the data already encodes it.

**Both target communes have a real, open (CC0), per-commune bulk dataset on data.public.lu:**
- Luxembourg City (commune code `C026`): [PAG Ville de Luxembourg](https://data.public.lu/en/datasets/pag-ville-de-luxembourg/) — `pag-c026.zip`, ~1.95GB, 572 files.
- Wiltz (commune code `C023`): [PAG WILTZ](https://data.public.lu/fr/datasets/pag-wiltz/) — `pag-c023.zip`, ~406MB, 124 files.

Each ZIP contains, per the dataset's own description, *"une partie graphique et écrite"*:
- **`pag_C0{23,26}.gml`**: real INTERLIS/GML vector data (EPSG:2169, matching our schema
  exactly — no reprojection needed), with feature classes including `ZONAGE` (base PAG
  zones), `ZONES_QE` (PAP Quartier Existant zones), `NQ_PAP` (PAP Nouveau Quartier),
  `PAP_APPROUVE` (approved PAP boundaries), `ZONES_SUPERPOSEES` (overlay constraints),
  `BATIMENT` (buildings, base map), and others.
- **`{code}_PE_*.docx`**: the real written-part documents, one per zone category (e.g.
  `026_PE_MIX_u.docx`, `023_PE_MIX_u.docx` — **both communes have a real MIX-u zone**;
  Luxembourg City additionally has `MIX_c` — Wiltz has `MIX_v` instead, consistent with
  Wiltz being a small/village-type commune with no railway-adjacent zone).
- **`{code}_PE_QE_*.docx`**: PAP QE written-part documents per zone sub-variant (e.g.
  `026_PE_QE_MIX_ud`, `026_PE_QE_MIX_uh` — confirms the video's MixU-D/E/S pattern, exact
  letters differ by commune).
- **`{code}_PAP_REF*.pdf` / `{code}_PE_PAP_REF*.pdf`**: individual approved PAP projects
  by reference number (graphic + written, paired) — Luxembourg City has ~90 of these;
  Wiltz has none in its bundle (smaller commune, less individual development).
- **`{code}_SD_PE_*.pdf`**: schémas directeurs (master plans) for NQ zones, named per
  neighbourhood (e.g. `026_SD_PE_Gasperich_GS_11_12_13...pdf`).
- **`{code}_QE_PAP_*.pdf`**: PAP QE graphic maps, named per locality (e.g.
  `026_QE_PAP_QE1_Nord.pdf`, matching the video's "Mersch-Réconge"-style locality naming).

**The key finding — document resolution is a real GIS attribute, not a visual lookup:**
- `ZONAGE` features carry `CATEGORIE` (zone code, e.g. `MIX_u`), an optional `GENRE`
  (sub-variant letter), and — critically — **`NOM_FICHIER`**, which names the *exact*
  written-part document for that polygon (verified: the real `MIX_u` polygon's
  `NOM_FICHIER` is literally `026_PE_MIX_u`, matching the file that exists in the same zip).
- `ZONES_QE` features carry **both** `NOM_FICHIER_EC` (written part, e.g.
  `026_PE_QE_MIX_ud`) **and** `NOM_FICHIER_GR` (graphic part, e.g.
  `026_QE_PAP_QE1_Nord`) — so PAP QE's document resolution (both parts) is *also* a direct
  attribute read, not a leader-line/annotation-matching problem.
- **Conclusion: resolving "which document(s) apply to this parcel" is a standard point-in-
  polygon spatial join** (parcel geometry vs. `ZONAGE`/`ZONES_QE` polygons, both already in
  EPSG:2169) **followed by reading an attribute** — the same kind of operation M1.4's
  overlay computation already does, not a new class of problem.

**Coefficients are real text/tables inside the DOCX, not separate GIS attributes** —
verified by fully extracting `026_PE_MIX_u.docx` (via `python-docx`): real legal article
text ("Art. 5 Zone mixte urbaine [MIX-u]"), and a real table mapping specific *schéma
directeur* codes (e.g. `SD GS-12`, `SD KI-11` — matching the `_SD_PE_*.pdf` filenames) to
minimum-residential-floor-area percentages (25% default, with overrides at 50/60/75% for
specific SDs). So the "0.3/0.5/0.6/20"-style numbers from the video are genuinely
document-text data, extracted the same way M5 extracted guichet.public.lu's text — table-
aware DOCX parsing, not a new architecture.

## IMPLEMENTED (2026-09-02): what actually landed, and what's still open

Built: `app/models/pag.py` (`PagZone`, `PapQeZone`), `ingestion/ingest_pag_zones.py`
(real ingestion, `make ingest-pag-zones`), `app/services/pag_zoning.py` (the real
spatial join), wired into `ParcelDetail.pag_zoning`. Verified live for the real "8 Rue
Beck" parcel: resolves to a real `FOR` (zone forestière) classification with the real
Art.19 legal text — see DECISIONS.md for why that's a genuine result, not a bug.

**Two real problems found and resolved during implementation, not anticipated here:**
- **A second, independent axis-order bug**: Wiltz's real GML export uses the opposite
  coordinate axis order from Luxembourg City's (Northing,Easting vs Easting,Northing) —
  confirmed live (0% parcel overlap as-parsed, exact bbox-swap match, fixed by swapping).
  `ingest_pag_zones.py::_resolve_axis_swap` now verifies empirically against each
  commune's own real parcels rather than assuming either order — see DECISIONS.md.
- **A real, partial data-completeness gap**: even after the axis fix, only 65.0%
  (Luxembourg City) / 53.8% (Wiltz) of real parcels intersect any ingested zone —
  confirmed via the live WMS (which shows real coverage the downloadable bulk file
  doesn't) to be a genuine gap in the *source* dataset, not our parsing. Reported as an
  honest empty result, not hidden or patched — see DECISIONS.md.

## RESOLVED (2026-09-03): the COS/CUS/CSS/DL coefficients

Prompted by a direct follow-up question ("retrieve the information for CUS, COS, CSS,
DL for a given PAP NQ"). This turned out **not** to need the DOCX-table parsing
originally assumed above — `NQ_PAP` ("Nouveau Quartier", not-yet-built zones) carries
these as genuine, populated GIS attributes: `COS_MIN`/`COS_MAX`, `CUS_MIN`/`CUS_MAX`,
`CSS_MAX` only (no `CSS_MIN` exists in the real data — no minimum soil-sealing
requirement), `DL_MIN`/`DL_MAX`. Verified live for both target communes — e.g. a real
Weimershof zone: COS≤0.6, CUS≤1.25, CSS≤0.8, DL≤115, matching the video's example
numbers ("0.3, 0.5, 0.6, 20"-style) almost exactly. Implemented as a new `pap_nq_zones`
table, ingested and spatially joined the same way as `pag_zones`/`pap_qe_zones` — see
DECISIONS.md. The zone's shared written regulation (`NOM_FICHIER_EC` — one generic
document per commune, not per-zone) is ingested and cited; the per-project schéma-
directeur PDF (`NOM_FICHIER_SD_EC`/`NOM_FICHIER_SD_GR`) remains a filename reference
only, same deliberate scope limit as PAP QE's graphic parts — the coefficients
themselves don't need it, only the fuller narrative text would.

## Still open / deliberately deferred

- Whether "the graphic part" should be served as the full source PDF/image, or a cropped
  excerpt around the parcel — not decided yet. PAP QE's graphic PDFs (`NOM_FICHIER_GR`)
  and NQ's schéma-directeur PDFs aren't fetched at all yet (~250MB for Luxembourg City's
  PAP QE graphics alone, no text extraction planned) — stored as real filename
  references only.
- `ZONES_SUPERPOSEES` (overlay constraints, 874 features in Luxembourg City's file) and
  `PAP_APPROUVE` haven't had their own attribute schemas inspected or ingested —
  `ZONAGE`, `ZONES_QE`, and `NQ_PAP` are now implemented; these two aren't.
- The DOCX table format for PAP QE's own per-sub-variant overrides (schéma-directeur →
  percentage, as opposed to NQ_PAP's clean GIS attributes) was only verified for one
  zone (`MIX_u`); other zone categories' documents may structure their tables
  differently. That raw table text is captured verbatim in every ingested document's
  chunk, but not parsed into structured fields yet.

## How this maps to existing phases

- **M2 (ingestion)**: for each of the two target communes, fetch the real PAG/PAP ZIP,
  parse the GML for `ZONAGE`/`ZONES_QE` polygons (with real provenance: commune, zone
  code, document filename), and ingest the referenced DOCX/PDF documents through the
  existing `sources`/`documents`/`chunks` schema — chunked per real legal article /
  document section, same discipline as M5's one-document ingestion, scaled up.
- **M3 (retrieval)**: given a parcel, spatial-join against the ingested `ZONAGE`/`ZONES_QE`
  geometries to resolve the zone code and exact document reference directly — this is a
  structured lookup, not a semantic-similarity guess, for the "which document applies"
  question. Semantic/hybrid search remains the right tool for open-ended questions asked
  *within* the resolved document(s).
