// Mirrors backend/app/schemas/{address,parcel}.py — kept in sync by hand for
// now (no OpenAPI codegen yet).

export interface AddressSearchResult {
  id: string;
  street_name: string;
  house_number: string;
  locality: string | null;
  postal_code: string | null;
  admin_commune_code: string | null;
  admin_commune_name: string | null;
  parcel_cadastral_id: string | null;
  lat: number;
  lon: number;
  score: number;
}

export interface ParcelSummary {
  cadastral_id: string;
  cadastral_commune_code: string;
  cadastral_commune_name: string;
  admin_commune_code: string | null;
  admin_commune_name: string | null;
  section_code: string;
  numero_principal: number;
  numero_secondaire: number;
  area_geom_m2: number;
}

export interface AddressSummary {
  id: string;
  street_name: string;
  house_number: string;
  locality: string | null;
}

export interface BuildingSummary {
  id: string;
  occupation_code: number | null;
  occupation_label: string | null;
  overlap_m2: number;
}

export interface OverlayConstraint {
  layer_code: string;
  label: string;
  category: string;
  intersects: boolean;
  overlap_m2: number | null;
  detail: Record<string, unknown> | null;
  source_url: string;
}

export interface OverlayLayerInfo {
  code: string;
  label: string;
  category: string;
  wms_layer_id: number;
  queryable: boolean;
  source_url: string;
}

export interface NeighbourDistance {
  cadastral_id: string;
  distance_m: number;
}

export interface SlopeResult {
  // All null together = no LiDAR coverage for this parcel (see DECISIONS.md)
  // — never a fabricated zero.
  avg_slope_pct: number | null;
  max_slope_pct: number | null;
  min_elevation_m: number | null;
  max_elevation_m: number | null;
  sample_pixel_count: number;
  source_url: string;
}

export interface ProcedureSectionInfo {
  heading: string;
  text: string;
}

export interface LegalReference {
  label: string;
  url: string;
}

export interface ProcedureDetail {
  title: string;
  source_url: string;
  publisher: string;
  document_date: string | null;
  sections: ProcedureSectionInfo[];
  legal_references: LegalReference[];
}

export interface BuildableEnvelope {
  setback_m: number;
  envelope_area_m2: number;
  is_empty: boolean;
  geometry_wgs84_geojson: Record<string, unknown> | null;
}

export interface ParcelDetail extends ParcelSummary {
  lieudit: string | null;
  nature_code: number | null;
  nature_label: string | null;
  area_declared_m2: number | null;
  addresses: AddressSummary[];
  buildings: BuildingSummary[];
  constraints: OverlayConstraint[];
  frontage_m: number;
  neighbours: NeighbourDistance[];
  // Passed straight through to ol/format/GeoJSON, which accepts any raw
  // GeoJSON object — no need for full GeoJSON types here.
  geometry_wgs84_geojson: Record<string, unknown>;
}

export interface ParcelIdentifyResponse {
  parcels: ParcelSummary[];
}
