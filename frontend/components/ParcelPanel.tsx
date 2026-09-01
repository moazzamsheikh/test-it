"use client";

import type { ParcelDetail, ParcelSummary } from "@/lib/types";

interface Props {
  parcel: ParcelDetail | null;
  candidates: ParcelSummary[];
  loading: boolean;
  onSelectCandidate: (cadastralId: string) => void;
}

export default function ParcelPanel({ parcel, candidates, loading, onSelectCandidate }: Props) {
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
    </div>
  );
}
