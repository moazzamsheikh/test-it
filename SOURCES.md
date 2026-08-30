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
