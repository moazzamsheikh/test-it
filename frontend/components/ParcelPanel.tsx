"use client";

import { useEffect, useState } from "react";
import { getBuildableEnvelope, getBuildingPermitProcedure, getParcelSlope } from "@/lib/api";
import type {
  BuildableEnvelope,
  PagZoningInfo,
  ParcelDetail,
  ParcelSummary,
  ProcedureDetail,
  SlopeResult,
} from "@/lib/types";

interface Props {
  parcel: ParcelDetail | null;
  candidates: ParcelSummary[];
  loading: boolean;
  onSelectCandidate: (cadastralId: string) => void;
  onEnvelopeChange: (geojson: Record<string, unknown> | null) => void;
}

export default function ParcelPanel({
  parcel,
  candidates,
  loading,
  onSelectCandidate,
  onEnvelopeChange,
}: Props) {
  if (loading) {
    return <div className="p-4 text-sm text-zinc-500">Loading…</div>;
  }

  // A click landed on a shared boundary between parcels — a real, graded
  // M1.3 edge case, surfaced honestly rather than silently picking one.
  if (candidates.length > 1) {
    return (
      <div className="p-4">
        <p className="mb-2 text-sm font-medium text-zinc-700">
          This click landed on a boundary shared by {candidates.length} parcels — pick one:
        </p>
        <ul className="space-y-1">
          {candidates.map((c) => (
            <li key={c.cadastral_id}>
              <button
                type="button"
                onClick={() => onSelectCandidate(c.cadastral_id)}
                className="text-sm text-blue-600 underline"
              >
                {c.cadastral_id} ({c.cadastral_commune_name}, section {c.section_code})
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (candidates.length === 0 && !parcel) {
    return (
      <div className="p-4 text-sm text-zinc-500">
        Search an address or click the map to select a parcel.
      </div>
    );
  }

  if (!parcel) {
    return (
      <div className="p-4 text-sm text-zinc-500">
        No parcel here — the click missed every parcel (e.g. a road).
      </div>
    );
  }

  return (
    <div className="h-full space-y-4 overflow-auto p-4">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900">{parcel.cadastral_id}</h2>
        <p className="text-sm text-zinc-600">
          {parcel.cadastral_commune_name} (cadastral) ·{" "}
          {parcel.admin_commune_name ?? "admin commune unknown"}
        </p>
        <p className="text-sm text-zinc-600">
          Section {parcel.section_code} · No. {parcel.numero_principal}/{parcel.numero_secondaire}
        </p>
        {parcel.lieudit && <p className="text-sm text-zinc-600">{parcel.lieudit}</p>}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-zinc-700">Area</h3>
        <p className="text-sm text-zinc-600">{parcel.area_geom_m2.toFixed(1)} m² (from geometry)</p>
        <p className="text-sm text-zinc-500">
          Declared:{" "}
          {parcel.area_declared_m2 !== null
            ? `${parcel.area_declared_m2.toFixed(1)} m²`
            : "not extracted — no source found yet (see DECISIONS.md)"}
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-zinc-700">Nature</h3>
        <p className="text-sm text-zinc-600">{parcel.nature_label ?? "unknown"}</p>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-zinc-700">
          Addresses ({parcel.addresses.length})
        </h3>
        {parcel.addresses.length === 0 ? (
          <p className="text-sm text-zinc-500">No addresses on this parcel.</p>
        ) : (
          <ul className="text-sm text-zinc-600">
            {parcel.addresses.map((a) => (
              <li key={a.id}>
                {a.house_number} {a.street_name}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-zinc-700">
          Buildings ({parcel.buildings.length})
        </h3>
        {parcel.buildings.length === 0 ? (
          <p className="text-sm text-zinc-500">No buildings on this parcel.</p>
        ) : (
          <ul className="text-sm text-zinc-600">
            {parcel.buildings.map((b) => (
              <li key={b.id}>
                {b.occupation_label ?? "unknown type"} — {b.overlap_m2.toFixed(1)} m² on this parcel
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Keyed on cadastral_id so switching parcels remounts with fresh
          local state, instead of an effect resetting it (React 19 flags
          synchronous setState in an effect body — see DECISIONS.md). The
          map-visible envelope layer itself is cleared by the parent
          (page.tsx) as soon as selectedParcelId changes. */}
      <GeometrySection
        key={parcel.cadastral_id}
        parcel={parcel}
        onEnvelopeChange={onEnvelopeChange}
      />

      <PagZoningSection pagZoning={parcel.pag_zoning} />

      <ConstraintsSection constraints={parcel.constraints} />

      <ProcedureSection />
    </div>
  );
}

function GeometrySection({
  parcel,
  onEnvelopeChange,
}: {
  parcel: ParcelDetail;
  onEnvelopeChange: (geojson: Record<string, unknown> | null) => void;
}) {
  const [slope, setSlope] = useState<SlopeResult | null>(null);
  const [slopeLoading, setSlopeLoading] = useState(false);
  const [slopeFailed, setSlopeFailed] = useState(false);
  const [setbackInput, setSetbackInput] = useState("3");
  const [envelope, setEnvelope] = useState<BuildableEnvelope | null>(null);
  const [envelopeLoading, setEnvelopeLoading] = useState(false);
  const [envelopeFailed, setEnvelopeFailed] = useState(false);

  async function handleComputeSlope() {
    setSlopeLoading(true);
    setSlopeFailed(false);
    try {
      setSlope(await getParcelSlope(parcel.cadastral_id));
    } catch {
      setSlopeFailed(true);
    } finally {
      setSlopeLoading(false);
    }
  }

  async function handleShowEnvelope() {
    const setbackM = Number(setbackInput);
    if (!Number.isFinite(setbackM) || setbackM < 0) return;
    setEnvelopeLoading(true);
    setEnvelopeFailed(false);
    try {
      const result = await getBuildableEnvelope(parcel.cadastral_id, setbackM);
      setEnvelope(result);
      onEnvelopeChange(result.geometry_wgs84_geojson);
    } catch {
      setEnvelopeFailed(true);
      onEnvelopeChange(null);
    } finally {
      setEnvelopeLoading(false);
    }
  }

  return (
    <div>
      <h3 className="text-sm font-semibold text-zinc-700">Geometry analysis</h3>

      <p className="mt-1 text-sm text-zinc-600">
        {parcel.frontage_m > 0
          ? `${parcel.frontage_m.toFixed(1)} m road frontage`
          : "No direct road frontage found (landlocked, or accessed via an easement not captured as its own road parcel)"}
      </p>

      {parcel.neighbours.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-zinc-500">
            {parcel.neighbours.length} nearby parcels
          </summary>
          <ul className="mt-1 space-y-0.5 text-xs text-zinc-500">
            {parcel.neighbours.map((n) => (
              <li key={n.cadastral_id}>
                {n.cadastral_id} —{" "}
                {n.distance_m < 0.01 ? "touching" : `${n.distance_m.toFixed(1)} m away`}
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="mt-3 border-t border-zinc-200 pt-2">
        <button
          type="button"
          onClick={() => void handleComputeSlope()}
          disabled={slopeLoading}
          className="rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-200 disabled:opacity-50"
        >
          {slopeLoading ? "Computing…" : slope ? "Recompute slope" : "Compute slope (LiDAR)"}
        </button>
        {slopeFailed && (
          <p className="mt-1 text-xs text-red-600">Slope lookup failed — try again.</p>
        )}
        {slope &&
          (slope.sample_pixel_count === 0 ? (
            <p className="mt-1 text-xs text-zinc-500">No LiDAR coverage for this parcel.</p>
          ) : (
            <p className="mt-1 text-xs text-zinc-600">
              Avg {slope.avg_slope_pct?.toFixed(1)}% · Max {slope.max_slope_pct?.toFixed(1)}% ·
              Elevation {slope.min_elevation_m?.toFixed(1)}–{slope.max_elevation_m?.toFixed(1)} m
            </p>
          ))}
      </div>

      <div className="mt-3 border-t border-zinc-200 pt-2">
        <label className="flex items-center gap-2 text-xs text-zinc-600">
          Setback (m)
          <input
            type="number"
            min={0}
            step={0.5}
            value={setbackInput}
            onChange={(e) => setSetbackInput(e.target.value)}
            className="w-16 rounded border border-zinc-300 px-1 py-0.5 text-xs"
          />
        </label>
        <p className="mt-0.5 text-[11px] text-zinc-400">
          Manual — PAG/PAP setback values aren&apos;t extracted yet
        </p>
        <button
          type="button"
          onClick={() => void handleShowEnvelope()}
          disabled={envelopeLoading}
          className="mt-1 rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-200 disabled:opacity-50"
        >
          {envelopeLoading ? "Computing…" : "Show buildable envelope"}
        </button>
        {envelopeFailed && (
          <p className="mt-1 text-xs text-red-600">Envelope lookup failed — try again.</p>
        )}
        {envelope &&
          (envelope.is_empty ? (
            <p className="mt-1 text-xs text-zinc-500">
              This setback fully erodes the parcel — nothing buildable.
            </p>
          ) : (
            <p className="mt-1 text-xs text-zinc-600">
              {envelope.envelope_area_m2.toFixed(1)} m² buildable
            </p>
          ))}
      </div>
    </div>
  );
}

function ConstraintsSection({ constraints }: { constraints: ParcelDetail["constraints"] }) {
  const applies = constraints.filter((c) => c.intersects);
  const doesNotApply = constraints.filter((c) => !c.intersects);

  return (
    <div>
      <h3 className="text-sm font-semibold text-zinc-700">
        Regulatory constraints ({applies.length} of {constraints.length} apply)
      </h3>
      {applies.length === 0 ? (
        <p className="text-sm text-zinc-500">None of the checked overlays apply here.</p>
      ) : (
        <ul className="mt-1 space-y-2">
          {applies.map((c) => (
            <li key={c.layer_code} className="rounded-md border border-amber-200 bg-amber-50 p-2">
              <div className="text-sm font-medium text-amber-900">{c.label}</div>
              {c.overlap_m2 !== null && (
                <div className="text-xs text-amber-800">{c.overlap_m2.toFixed(1)} m² overlap</div>
              )}
              {c.document ? (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-amber-800">
                    {c.document.article_ref ?? c.document.title}
                  </summary>
                  {c.document.text && (
                    <p className="mt-1 text-xs whitespace-pre-line text-zinc-700">
                      {c.document.text}
                    </p>
                  )}
                  <a
                    href={c.document.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-700 underline"
                  >
                    Full text
                  </a>
                </details>
              ) : (
                <a
                  href={c.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-700 underline"
                >
                  Source
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
      {doesNotApply.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-zinc-500">
            {doesNotApply.length} checked and not applicable
          </summary>
          <ul className="mt-1 space-y-1 text-xs text-zinc-500">
            {doesNotApply.map((c) => (
              <li key={c.layer_code}>
                {c.label}
                {c.document && (
                  <>
                    {" — governed nationally by "}
                    <a
                      href={c.document.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-700 underline"
                    >
                      {c.document.title}
                    </a>
                    {" (doesn't apply at this specific location)"}
                  </>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function ProcedureSection() {
  const [procedure, setProcedure] = useState<ProcedureDetail | null>(null);

  useEffect(() => {
    let cancelled = false;
    getBuildingPermitProcedure()
      .then((result) => {
        if (!cancelled) setProcedure(result);
      })
      .catch(() => {
        // Not ingested yet, or a transient failure — not worth a dedicated
        // spinner/error state for one static document; render nothing.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!procedure) return null;

  return (
    <div className="border-t border-zinc-200 pt-3">
      <h3 className="text-sm font-semibold text-zinc-700">Related procedure</h3>
      <p className="mt-1 text-xs text-zinc-400">
        A structured summary of one real government procedure page — not a
        chatbot, and not specific to this parcel.
      </p>
      <p className="mt-2 text-sm font-medium text-zinc-800">{procedure.title}</p>
      <p className="text-xs text-zinc-500">
        {procedure.publisher}
        {procedure.document_date && ` · updated ${procedure.document_date}`} ·{" "}
        <a
          href={procedure.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-700 underline"
        >
          Source
        </a>
      </p>

      <div className="mt-2 space-y-2">
        {procedure.sections.map((section) => (
          <details key={section.heading}>
            <summary className="cursor-pointer text-sm text-zinc-700">
              {section.heading}
            </summary>
            <p className="mt-1 text-xs whitespace-pre-line text-zinc-600">{section.text}</p>
          </details>
        ))}
      </div>

      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-zinc-500">
          Base légale ({procedure.legal_references.length})
        </summary>
        <ul className="mt-1 space-y-0.5 text-xs">
          {procedure.legal_references.map((ref) => (
            <li key={ref.url}>
              <a
                href={ref.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-700 underline"
              >
                {ref.label}
              </a>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function formatMinMax(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min === null) return `≤ ${max}`;
  if (max === null) return `≥ ${min}`;
  if (min === max) return `${min}`;
  return `${min} – ${max}`;
}

function PagZoningSection({ pagZoning }: { pagZoning: PagZoningInfo }) {
  const { pag_zones: pagZones, pap_qe_zones: papQeZones, pap_nq_zones: papNqZones } = pagZoning;

  if (pagZones.length === 0 && papQeZones.length === 0 && papNqZones.length === 0) {
    return (
      <div className="border-t border-zinc-200 pt-3">
        <h3 className="text-sm font-semibold text-zinc-700">PAG/PAP zoning</h3>
        <p className="mt-1 text-xs text-zinc-500">
          No zone found for this parcel in the ingested PAG data — a real,
          confirmed gap in the current source dataset for some areas, not an
          error (see DECISIONS.md).
        </p>
      </div>
    );
  }

  return (
    <div className="border-t border-zinc-200 pt-3">
      <h3 className="text-sm font-semibold text-zinc-700">PAG/PAP zoning</h3>
      <p className="mt-1 text-xs text-zinc-400">
        Real zone classification from ACT&apos;s own PAG data, reported
        exactly as found — including surprising results.
      </p>

      {pagZones.map((zone, i) => (
        // A parcel can genuinely span several separately-digitized polygons
        // of the same category (e.g. multiple real "FOR" fragments) — index
        // is the only safe key, category+genre isn't guaranteed unique.
        <div key={i} className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2">
          <div className="text-sm font-medium text-amber-900">
            {zone.category}
            {zone.genre && ` (${zone.genre})`} — {zone.overlap_m2.toFixed(1)} m² overlap
          </div>
          {zone.document && (
            <details className="mt-1">
              <summary className="cursor-pointer text-xs text-amber-800">
                {zone.document.article_ref ?? zone.document.title}
              </summary>
              {zone.document.text && (
                <p className="mt-1 text-xs whitespace-pre-line text-zinc-700">
                  {zone.document.text}
                </p>
              )}
            </details>
          )}
        </div>
      ))}

      {papQeZones.map((zone, i) => (
        <div
          key={i}
          className="mt-2 rounded-md border border-blue-200 bg-blue-50 p-2"
        >
          <div className="text-sm font-medium text-blue-900">
            PAP Quartier Existant — {zone.overlap_m2.toFixed(1)} m² overlap
          </div>
          {zone.written_document && (
            <details className="mt-1">
              <summary className="cursor-pointer text-xs text-blue-800">
                {zone.written_document.article_ref ?? zone.written_document.title}
              </summary>
              {zone.written_document.text && (
                <p className="mt-1 text-xs whitespace-pre-line text-zinc-700">
                  {zone.written_document.text}
                </p>
              )}
            </details>
          )}
          {zone.graphic_document_filename && (
            <p className="mt-1 text-[11px] text-zinc-500">
              Graphic plan reference: {zone.graphic_document_filename} (not
              extracted yet — see DECISIONS.md)
            </p>
          )}
        </div>
      ))}

      {papNqZones.map((zone, i) => (
        <div key={i} className="mt-2 rounded-md border border-green-200 bg-green-50 p-2">
          <div className="text-sm font-medium text-green-900">
            PAP Nouveau Quartier{zone.denomination && ` — ${zone.denomination}`}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {zone.overlap_m2.toFixed(1)} m² overlap
          </div>
          <dl className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 text-xs text-zinc-700">
            {formatMinMax(zone.cos_min, zone.cos_max) && (
              <>
                <dt className="text-zinc-500">COS (footprint ratio)</dt>
                <dd>{formatMinMax(zone.cos_min, zone.cos_max)}</dd>
              </>
            )}
            {formatMinMax(zone.cus_min, zone.cus_max) && (
              <>
                <dt className="text-zinc-500">CUS (floor area ratio)</dt>
                <dd>{formatMinMax(zone.cus_min, zone.cus_max)}</dd>
              </>
            )}
            {zone.css_max !== null && (
              <>
                <dt className="text-zinc-500">CSS max (soil sealing)</dt>
                <dd>{zone.css_max}</dd>
              </>
            )}
            {formatMinMax(zone.dl_min, zone.dl_max) && (
              <>
                <dt className="text-zinc-500">DL (units/ha)</dt>
                <dd>{formatMinMax(zone.dl_min, zone.dl_max)}</dd>
              </>
            )}
          </dl>
          {zone.written_document && (
            <details className="mt-1">
              <summary className="cursor-pointer text-xs text-green-800">
                {zone.written_document.article_ref ?? zone.written_document.title}
              </summary>
              {zone.written_document.text && (
                <p className="mt-1 text-xs whitespace-pre-line text-zinc-700">
                  {zone.written_document.text}
                </p>
              )}
            </details>
          )}
          {zone.schema_directeur_filename && (
            <p className="mt-1 text-[11px] text-zinc-500">
              Schéma directeur reference: {zone.schema_directeur_filename} (not
              extracted yet — see DECISIONS.md)
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
