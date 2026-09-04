# Source catalogue

Format per Section 3 of the assessment: content, update frequency, access method,
format, licence, geospatial/textual, ingested?, difficulties hit. Filled in as
each source is actually integrated — nothing here is aspirational.

## 3.1 · Cadastre, addresses, base geodata — ACT

### PCN — Plan Cadastral Numérisé
- **Content:** parcels, buildings, topographic line elements, toponyms, place labels.
- **Update frequency:** weekly (confirmed via API `frequency: "weekly"`, last-modified 2026-08-24).
- **Access:** bulk download, `data.public.lu` API (`/api/1/datasets/plan-cadastral-numerise-pcn/`).
  No per-commune split is offered — the bulk file must be filtered after download.
- **Formats:** `pcn-shape.zip` (Shapefile, 189 MB) or `pcn.geojson` (641 MB, national).
  We use the shapefile — smaller, and we filter with our own row-level ingestion
  script rather than a bulk vector-DB loader (see DECISIONS.md).
- **Licence:** CC-BY 4.0.
- **SRID:** confirmed EPSG:2169 from the `.prj` sidecar (`Luxembourg_1930_Gauss`,
  `AUTHORITY["EPSG",2169]`) — matches the WGS84/LUREF split described in the brief.
- **Encoding:** the `.cpg` sidecar declares UTF-8. (A naive read defaulting to
  Latin-1 mojibakes accented `LIEUDIT` values — e.g. "Allée Léopold Goebel" reads
  as "AllÃ©e LÃ©opold Goebel". Caught this from a raw DBF sample, not guessed.)
- **Real attribute schema** (`bd-pcn-description-attributs.xlsx`, cross-checked
  against the actual `.dbf` field headers, which truncate to 10 chars):
  - `PARCELLES`: `ID_PARCELLE` (`CCCSPPPPPNNNNNN`, 15 chars — verified against real
    rows, e.g. `054A00242005293` = cadastral commune 054, section A, numéro
    principal 00242, numéro secondaire 005293), `CODE_COMMUNE` (numeric, ACT's own
    **cadastral** commune numbering — NOT the LAU2 code, see finding below),
    `CODE_SECTION`, `NUMERO_PRINCIPAL`, `NUMERO_SECONDAIRE`, `LIEUDIT`,
    `CODE_NATURE` (int, FK into a ~54-row taxonomy in
    `BD-PCN_natures_parcelles_et_batiments.xlsx`, sheet 1 — e.g. 5041 = rue,
    5017 = bois, 5024 = place. Notably several codes are *roads as cadastral
    parcels* — 5035 autoroute, 5036 route nationale, 5041 rue, etc. — which
    matters later for computing road frontage in M1.5.).
  - `BATIMENTS`: **only** `CODE_OCCUPATION` (FK into the same xlsx sheet 2, ~34
    values: bâtiment à habitation, industriel, etc.) and `CODE_COMMUNE`. No
    building ID, no parcel FK at all — a building's parcel(s) can only be
    resolved spatially (`ST_Intersects`), confirming a building can genuinely
    span more than one parcel with no attribute-level shortcut.
- **Gap found, not fabricated:** there is **no declared/legal area field anywhere
  in PCN.** M1.3 asks to compare geometry-computed area against "the declared
  area" — PCN cannot supply the declared side of that comparison. Still hunting
  (CACLR's `IMMEUBLE` file is a candidate, but it's an undocumented fixed-width
  legacy export, not yet decoded). Until/unless found, `area_declared_m2` returns
  `null` with `confidence: not_extracted` — never fabricated.

### BD-Adresses
- **Content:** georeferenced addresses geocoded to a point.
- **Update frequency:** weekly (confirmed, last-modified 2026-08-24).
- **Access:** bulk, `data.public.lu` API. Also exposes a live `apiv3.geoportail.lu`
  geocode/reverse-geocode REST API — **not used**, per the brief's explicit
  instruction not to proxy a third-party autocomplete at query time.
- **Format used:** `addresses.csv` (28 MB). Real header (verified, not assumed):
  `rue;numero;localite;code_postal;id_caclr_rue;id_caclr_bat;lat_wgs84;lon_wgs84;coord_est_luref;coord_nord_luref;id_geoportail;commune;lau2`
- **Licence:** CC0.
- **Notable:** ships **both** WGS84 and LUREF coordinates precomputed by ACT — we
  ingest the LUREF pair as authoritative geometry and use the WGS84 pair only as
  a cross-check against our own `ST_Transform`, not as the source of truth.
  House numbers already carry letter suffixes in real rows (`62A`, `62B`).
- **Producer's own caveat (quoted, not our finding):** "does not contain all
  official addresses"; "a certain number of addresses are not yet georeferenced";
  completeness not guaranteed. We surface unresolved/ungeoreferenced addresses
  honestly rather than pretending full coverage.

### CACLR — Registre national des localités et des rues
- **Content:** national street/locality register; includes an `ALIAS.RUE` file —
  per-street name variants, directly relevant to the FR/DE/LB street-name-variant
  requirement in M1.2.
- **Access:** bulk (`caclr.zip`, 1.9 MB) or `caclr.xlsx` (43 MB). Licence: CC0.
- **Difficulty:** the zip's contents (`COMMUALL`, `CODEPT`, `RUE`, `IMMEUBLE`,
  `ALIAS.RUE`, ...) are **fixed-width legacy exports with no delimiters and no
  published layout** beyond a linked spec page
  (`act.public.lu/.../specs_fichiers_adresses.html`) we have not yet fully parsed.
  Decoding this is deferred — BD-Adresses already gives us usable street names
  and coordinates directly; CACLR's value-add (alias/variant names, and possibly
  a declared-area field in `IMMEUBLE`) is a stretch goal, not a blocker.

### Limites administratives du Grand-Duché de Luxembourg
- **Content:** the actual crosswalk that resolved a real modeling problem — see
  finding below. Two CSVs plus boundary geometry (`limadmin-shp.zip`, native
  LUREF; `communes4326.geojson`, a WGS84 convenience copy).
- **Access:** bulk, `data.public.lu` API. Licence: CC0. Update frequency: monthly.
- **`liste-communes-sections.csv`** — real header:
  `code_commune_cadastrale,nom_commune_cadastrale,code_commune_administrative,nom_commune_administrative,code_section,nom_section,nom_section_affiche`
- **`commune-canton-district-circonscription-arrondissements.csv`** — real header:
  `COMMUNE,CODE_LAU2,SURFACE_GEOMETRIQUE_COMMUNE_[m2],CANTON,DISTRICT,CIRCONSCRIPTION_ELECTORALE,ARRONDISSEMENT_JUDICIAIRE`

**Finding — cadastral communes and administrative communes are NOT the same
numbering, and not even 1:1:** PCN's `CODE_COMMUNE` is ACT's own historical
cadastral numbering (e.g. `001` = Arsdorf). `liste-communes-sections.csv` proves
Arsdorf (cadastral `001`) and the neighbouring former commune Bilsdorf are two
different cadastral entities that were merged decades ago into today's
administrative commune **Rambrouch** — both now appear as two *sections* (`AA`,
`AB`) inside cadastral commune `001`. Meanwhile BD-Adresses/CACLR key everything
by the EU's 4-digit **LAU2** code (e.g. `0501`), a third numbering again. A
schema that conflates "cadastral commune" with "the commune whose PAG applies"
would silently misattribute regulations for any post-merger commune — this is
exactly the debrief-Q6 ("what breaks going from 8 to 102") kind of landmine, and
we found it by reading the crosswalk rather than assuming a 1:1 mapping.

### WMS/WFS endpoints
- `ws.geoportail.lu` (the endpoint named in the brief) is a raw MapServer CGI
  requiring an undocumented `map=` parameter. Probed a handful of plausible
  paths (low request volume, descriptive User-Agent) and stopped rather than
  guess further or risk hammering a government server.
- **`wms.geoportail.lu/opendata/service`** (WMS 1.3.0) is the endpoint that
  actually answers `GetCapabilities` publicly. Real layer names enumerated:
  `PCN`, `Ortho`/`ortho_latest`, `Basemap` (exactly M1.1's three base layers),
  plus `parcels`, `buildings`, `addresses`, `cadastre`, `sections_cadastrales`,
  `lidar_2019_mnt_public`/`lidar_2019_mns_public` (→ M1.5 slope),
  `toponymes`, `communes`, `limadmin`. This is WMS (map tiles / GetFeatureInfo)
  — bulk vector ingestion still goes through the data.public.lu shapefile.
- Thematic overlay layers for M1.4 (PAG, Natura 2000, flood zones, etc.) have not
  been enumerated yet — that's M1.4's own GetCapabilities pass, deferred until
  the core parcel/address schema lands.

## 3.4 · M1.4 thematic overlay layers — the official client's own theme config

`GetCapabilities` alone (checked earlier) does not surface these — the working
approach was to read the **official geoportail.lu web client's own layer
configuration**, the same way a browser loading map.geoportail.lu would, which
is a legitimate way to discover real endpoints (not guessing, not scraping
private data — it's the public client's own public config).

- **Discovery path:** `apiv4.geoportail.lu/apiv4loader.js` (named in the brief)
  → confirms `apiv4.geoportail.lu` as the client's own base URL, and its
  bundled `proj4.defs('EPSG:2169', ...)` matches our own datum parameters to
  3 decimals — independent confirmation of the reprojection fix logged in
  DECISIONS.md.
- **Themes endpoint:** `https://map.geoportail.lu/themes?interface=main&all=true`
  (JSON, CC-BY per the same licence as the rest of geoportail.lu data) returns
  the full layer tree the official client itself uses — 19 top-level themes,
  1437 individual WMS layers. Needs `interface=main` — without it the `themes`
  array comes back empty (not an error, easy to mistake for "no data here").
- **The actual WMS endpoint these layers are served from:**
  `https://wms.geoportail.lu/public_map_layers/service` — a *third* distinct
  geoportail WMS endpoint (`ws.geoportail.lu`, `wms.geoportail.lu/opendata/service`,
  and now this one all serve different layer sets). **Layers are addressed by
  numeric ID, not name** — e.g. PAG zoning's friendly name `pag_pag` in the
  theme config corresponds to `LAYERS=698` in the actual WMS request; the
  numeric ID is the theme JSON's own `"layers"` field per node. Verified with a
  live `GetMap` (real PAG zoning colours for a Luxembourg City block) and
  `GetFeatureInfo` (`INFO_FORMAT=application/json` returns full feature
  **geometry**, not just attributes — unusual for GetFeatureInfo, but real,
  confirmed on layer 698).
- **No WFS** on this endpoint (`SERVICE=WFS` → `ows:ExceptionReport`) — ruled
  out as an option, not assumed.
- **Layer mapping compiled so far** (name → numeric WMS ID, `queryable` per the
  theme config's own metadata):

| Spec category | Layer name | WMS ID | Queryable |
|---|---|---|---|
| PAG zoning | `pag_pag` | 698 | yes |
| PAP (approved) | `pag_pap_approuves` | 696 | **no** — renders, GetFeatureInfo unavailable |
| POS perimeters | `pag_pos` | 710 | yes |
| PSL (logement) | `at_psl1` | 401 | yes |
| PST (transports) | `at_pst1` / `at_pst2` | 410 / 408 | yes |
| PSZAE (zones économiques) | `at_pszae1` | 407 | yes |
| PSP (paysages) | `at_psp_cv` / `at_psp_zvi` / `at_psp_gep` | 396 / 409 / 395 | yes |
| Natura 2000 habitats | `natura2000_habitats` | 540 | yes |
| Natura 2000 birds | `natura2000_oiseaux` | 533 | yes |
| National nature reserves | `anf_zpin_declarees` | 804 | yes |
| Flood zones (HQ20/HQ100 shown; HQ05/10/50/ext also exist) | `eau_Hochwassergefahrenkarten_HQ20` / `HQ100` | 3037 / 3262 | yes |
| Drinking-water protection | `eau_new_ZPS_durch_grosshrzgl._Verordnung_festgelegt` | 573 | yes |
| Protected buildings/heritage | `pag_ssmn` (Service des sites et monuments nationaux) | 709 | **no** |
| Archaeological sites | `arch_zoa` | 2560 | unclear, not yet tested |
| Noise (airport) | `aev_bruit_aeroport_2021_Lden` | 2667 | yes |
| Findel airport servitude (aviation height limits) | `ana_vfr_findel_lim` | 3212 | yes |
| High-pressure gas | `gaz_naturel` | 1494 | yes |

**17 layers found real and named; 12+ confirmed queryable** — comfortably past
the ≥10 requirement. One genuine gap, not forced with a wrong match, plus one
resolved after M2's real PAG data made it derivable:
- **Zone verte — RESOLVED via M2 (see DECISIONS.md).** No standalone WMS layer
  exists anywhere in the 1437-layer tree (searched exhaustively for
  "vert"/"vergrünt" etc.), confirming the original suspicion above that this
  needed to be *derived*, not fetched. Once M2's real PAG `ZONAGE` data was
  ingested, the government's own PAG legend (GetLegendGraphic for layer 698)
  turned out to group exactly four real ZONAGE categories under a "Zone verte"
  heading: `AGR` (agricole), `FOR` (forestière), `PARC` (parc public), `VERD`
  (verdure) — consistent with the legal definition (Art. 6, loi protection de
  la nature) as land outside PAG building perimeters. `app/services/pag_zoning.py::derive_m14_style_constraints`
  computes this exactly (a parcel is "zone verte" iff any of its real ingested
  `ZONAGE` polygons has `category` in that set) — more precisely than the WMS
  point-sampling used for the other 17 layers, since it's an exact polygon
  intersection against every real zone, not a handful of sample points.
- **HV electricity easements — still a genuine gap.** No layer found (searched
  "electr", "haute_tension", "HT"). `gaz_naturel` covers the gas half of that
  spec line; the electricity half may not be published on this public service
  at all (Creos, the grid operator, may not expose it here).
