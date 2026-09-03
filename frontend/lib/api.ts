import type {
  AddressSearchResult,
  BuildableEnvelope,
  OverlayLayerInfo,
  ParcelDetail,
  ParcelIdentifyResponse,
  ParcelSummary,
  ProcedureDetail,
  SlopeResult,
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

/** Separate from getParcelDetail on purpose — an uncached slope lookup is a
 * multi-second remote LiDAR read, so it's fetched lazily on demand rather
 * than blocking the rest of the side panel (see backend DECISIONS.md). */
export function getParcelSlope(cadastralId: string): Promise<SlopeResult> {
  return getJson<SlopeResult>(`/api/v1/parcels/${encodeURIComponent(cadastralId)}/slope`, {});
}

/** PAG/PAP setback values aren't reliably extractable yet, so setbackM is a
 * manual value the user enters — not a fabricated default (see DECISIONS.md). */
export function getBuildableEnvelope(
  cadastralId: string,
  setbackM: number,
): Promise<BuildableEnvelope> {
  return getJson<BuildableEnvelope>(
    `/api/v1/parcels/${encodeURIComponent(cadastralId)}/buildable-envelope`,
    { setback_m: setbackM },
  );
}

/** M5 — a structured, citation-backed display of one real ingested
 * government procedure (not a chatbot; see backend DECISIONS.md). Not
 * parcel-specific: fetched once, independent of which parcel is selected. */
export async function getBuildingPermitProcedure(): Promise<ProcedureDetail | null> {
  const response = await fetch(`${API_BASE}/api/v1/procedures/building-permit`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`procedure lookup failed: HTTP ${response.status}`);
  }
  return (await response.json()) as ProcedureDetail;
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
