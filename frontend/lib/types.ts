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

export interface ParcelDetail extends ParcelSummary {
  lieudit: string | null;
  nature_code: number | null;
  nature_label: string | null;
  area_declared_m2: number | null;
  addresses: AddressSummary[];
  buildings: BuildingSummary[];
  // Passed straight through to ol/format/GeoJSON, which accepts any raw
  // GeoJSON object — no need for full GeoJSON types here.
  geometry_wgs84_geojson: Record<string, unknown>;
}

export interface ParcelIdentifyResponse {
  parcels: ParcelSummary[];
}
