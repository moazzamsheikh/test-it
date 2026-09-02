import type {
  AddressSearchResult,
  OverlayLayerInfo,
  ParcelDetail,
  ParcelIdentifyResponse,
  ParcelSummary,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getJson<T>(path: string, params: Record<string, string | number>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, String(value));
  }
  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`${path} failed: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export function searchAddresses(q: string, limit = 10): Promise<AddressSearchResult[]> {
  return getJson<AddressSearchResult[]>("/api/v1/addresses/search", { q, limit });
}

/** lon/lat in WGS84 (EPSG:4326) — the backend transforms to LUREF server-side. */
export function identifyParcel(lon: number, lat: number): Promise<ParcelIdentifyResponse> {
  return getJson<ParcelIdentifyResponse>("/api/v1/parcels/identify", { lon, lat });
}

export function findParcelByReference(
  cadastralCommuneCode: string,
  sectionCode: string,
  numeroPrincipal: number,
  numeroSecondaire?: number,
): Promise<ParcelSummary[]> {
  const params: Record<string, string | number> = {
    cadastral_commune_code: cadastralCommuneCode,
    section_code: sectionCode,
    numero_principal: numeroPrincipal,
  };
  if (numeroSecondaire !== undefined) {
    params.numero_secondaire = numeroSecondaire;
  }
  return getJson<ParcelSummary[]>("/api/v1/parcels/by-reference", params);
}

export async function getOverlayLayers(): Promise<OverlayLayerInfo[]> {
  const response = await fetch(`${API_BASE}/api/v1/overlays`);
  if (!response.ok) {
    throw new Error(`overlay layers failed: HTTP ${response.status}`);
  }
  return (await response.json()) as OverlayLayerInfo[];
}

export async function getParcelDetail(cadastralId: string): Promise<ParcelDetail | null> {
  const url = `${API_BASE}/api/v1/parcels/${encodeURIComponent(cadastralId)}`;
  const response = await fetch(url);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`parcel detail failed: HTTP ${response.status}`);
  }
  return (await response.json()) as ParcelDetail;
}
