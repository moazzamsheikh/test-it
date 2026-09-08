"use client";

import { useState, type FormEvent } from "react";
import { findParcelByReference } from "@/lib/api";
import type { ParcelSummary } from "@/lib/types";

interface Props {
  /** Same shape as map-click identify: 0/1/many are all real outcomes, not
   * something this component resolves itself (see M1.3 DECISIONS.md). */
  onResult: (parcels: ParcelSummary[]) => void;
}

/** M1.3's cadastral-reference search — an architect who already knows the
 * commune/section/parcel number, not an address (the real motivating case:
 * forest/countryside parcels with no address at all). The backend endpoint
 * has existed since M1.3; this UI was the missing half. */
export default function ReferenceSearch({ onResult }: Props) {
  const [communeCode, setCommuneCode] = useState("");
  const [sectionCode, setSectionCode] = useState("");
  const [numeroPrincipal, setNumeroPrincipal] = useState("");
  const [numeroSecondaire, setNumeroSecondaire] = useState("");
  const [notFound, setNotFound] = useState(false);

  const canSubmit =
    communeCode.trim() !== "" && sectionCode.trim() !== "" && numeroPrincipal.trim() !== "";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setNotFound(false);
    const parcels = await findParcelByReference(
      communeCode.trim(),
      sectionCode.trim().toUpperCase(),
      Number(numeroPrincipal),
      numeroSecondaire.trim() === "" ? undefined : Number(numeroSecondaire),
    );
    if (parcels.length === 0) setNotFound(true);
    onResult(parcels);
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-1.5 text-sm">
      <span className="text-xs whitespace-nowrap text-zinc-500">By reference:</span>
      <input
        value={communeCode}
        onChange={(e) => setCommuneCode(e.target.value)}
        placeholder="Commune"
        className="w-16 rounded-md border border-zinc-300 px-2 py-1.5 text-xs focus:border-zinc-500 focus:outline-none"
      />
      <input
        value={sectionCode}
        onChange={(e) => setSectionCode(e.target.value)}
        placeholder="Sec."
        className="w-12 rounded-md border border-zinc-300 px-2 py-1.5 text-xs focus:border-zinc-500 focus:outline-none"
      />
      <input
        value={numeroPrincipal}
        onChange={(e) => setNumeroPrincipal(e.target.value)}
        placeholder="No."
        inputMode="numeric"
        className="w-16 rounded-md border border-zinc-300 px-2 py-1.5 text-xs focus:border-zinc-500 focus:outline-none"
      />
      <input
        value={numeroSecondaire}
        onChange={(e) => setNumeroSecondaire(e.target.value)}
        placeholder="Sub"
        inputMode="numeric"
        className="w-14 rounded-md border border-zinc-300 px-2 py-1.5 text-xs focus:border-zinc-500 focus:outline-none"
      />
      <button
        type="submit"
        disabled={!canSubmit}
        className="rounded-md border border-zinc-300 bg-zinc-50 px-2 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-40"
      >
        Find
      </button>
      {notFound && <span className="text-xs text-red-600">No match</span>}
    </form>
  );
}
