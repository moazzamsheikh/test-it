"use client";

import { useEffect, useState } from "react";
import { searchAddresses } from "@/lib/api";
import type { AddressSearchResult } from "@/lib/types";

interface Props {
  onSelect: (address: AddressSearchResult) => void;
}

const DEBOUNCE_MS = 250;
const MIN_QUERY_LENGTH = 2;

export default function AddressSearch({ onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AddressSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const queryTooShort = query.trim().length < MIN_QUERY_LENGTH;

  useEffect(() => {
    if (queryTooShort) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      // Only flip the loading indicator once the debounce actually fires —
      // a query that gets superseded before then never flickers "loading".
      setLoading(true);
      searchAddresses(query)
        .then((found) => {
          if (cancelled) return;
          setResults(found);
          setOpen(true);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, queryTooShort]);

  // Derived, not stored: no separate reset step needed when the query gets
  // too short to search again.
  const visibleResults = queryTooShort ? [] : results;

  return (
    <div className="relative w-full max-w-md">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => visibleResults.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="1 Rue du Fort Thüngen, Luxembourg"
        className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none"
      />
      {loading && (
        <span className="absolute top-2.5 right-3 text-xs text-zinc-400">…</span>
      )}
      {open && visibleResults.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border border-zinc-200 bg-white shadow-lg">
          {visibleResults.map((address) => (
            <li key={address.id}>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-zinc-100"
                onClick={() => {
                  onSelect(address);
                  setQuery(`${address.house_number} ${address.street_name}`);
                  setOpen(false);
                }}
              >
                <div className="font-medium text-zinc-900">
                  {address.house_number} {address.street_name}
                </div>
                <div className="text-xs text-zinc-500">
                  {address.locality ?? address.admin_commune_name} · {address.postal_code}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
