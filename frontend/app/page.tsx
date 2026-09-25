"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import AddressSearch from "@/components/AddressSearch";
import ParcelPanel from "@/components/ParcelPanel";
import ReferenceSearch from "@/components/ReferenceSearch";
import { getParcelDetail, identifyParcel } from "@/lib/api";
import type { AddressSearchResult, ParcelDetail, ParcelSummary } from "@/lib/types";

// OpenLayers touches `window`/`document` at construction time — load it only
// on the client, never during server-side rendering.
const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });
// ChatPanel reads localStorage in its initial state (see its own comment)
// — same client-only constraint as MapView, same fix.
const ChatPanel = dynamic(() => import("@/components/ChatPanel"), { ssr: false });

export default function Home() {
  const [selectedParcelId, setSelectedParcelId] = useState<string | null>(null);
  const [parcelDetail, setParcelDetail] = useState<ParcelDetail | null>(null);
  const [candidates, setCandidates] = useState<ParcelSummary[]>([]);
  const [flyTo, setFlyTo] = useState<{ lon: number; lat: number } | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [envelopeGeojson, setEnvelopeGeojson] = useState<Record<string, unknown> | null>(null);
  const [chatVisible, setChatVisible] = useState(true);
  const [parcelPanelVisible, setParcelPanelVisible] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function loadDetail() {
      // A different parcel is being loaded (or none at all) — any envelope
      // computed for the previous parcel no longer applies.
      setEnvelopeGeojson(null);
      if (!selectedParcelId) {
        setParcelDetail(null);
        return;
      }
      setLoadingDetail(true);
      try {
        const detail = await getParcelDetail(selectedParcelId);
        if (!cancelled) setParcelDetail(detail);
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    }
    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedParcelId]);

 // Click Map to identify a parcel. If multiple parcels are returned, let the user pick one.
  async function handleMapClick(lon: number, lat: number) {
    const { parcels } = await identifyParcel(lon, lat);
    if (parcels.length === 1) {
      setCandidates([]);
      setSelectedParcelId(parcels[0].cadastral_id);
    } else if (parcels.length > 1) {
      // Landed exactly on a shared boundary — let the user pick, don't guess.
      setCandidates(parcels);
      setSelectedParcelId(null);
    } else {
      // Missed every parcel (e.g. a road) — a real outcome, not an error.
      setCandidates([]);
      setSelectedParcelId(null);
    }
  }

  function handleSelectAddress(address: AddressSearchResult) {
    setFlyTo({ lon: address.lon, lat: address.lat });
    setCandidates([]);
    setSelectedParcelId(address.parcel_cadastral_id);
  }

  function handleSelectCandidate(cadastralId: string) {
    setCandidates([]);
    setSelectedParcelId(cadastralId);
  }

  function handleReferenceResult(parcels: ParcelSummary[]) {
    if (parcels.length === 1) {
      setCandidates([]);
      setSelectedParcelId(parcels[0].cadastral_id);
    } else if (parcels.length > 1) {
      setCandidates(parcels);
      setSelectedParcelId(null);
    } else {
      setCandidates([]);
      setSelectedParcelId(null);
    }
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-4 border-b border-zinc-200 px-4 py-3">
        <h1 className="text-sm font-semibold whitespace-nowrap text-zinc-900">
          Luxembourg Parcel Intelligence
        </h1>
        <AddressSearch onSelect={handleSelectAddress} />
        <ReferenceSearch onResult={handleReferenceResult} />
        <div className="ml-auto flex gap-2">
          {!parcelPanelVisible && (
            <button
              type="button"
              onClick={() => setParcelPanelVisible(true)}
              className="rounded border border-zinc-300 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-100"
            >
              Show parcel details
            </button>
          )}
          {!chatVisible && (
            <button
              type="button"
              onClick={() => setChatVisible(true)}
              className="rounded border border-zinc-300 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-100"
            >
              Show chat
            </button>
          )}
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1">
          <MapView
            parcelDetail={parcelDetail}
            flyTo={flyTo}
            envelopeGeojson={envelopeGeojson}
            onMapClick={handleMapClick}
          />
        </main>
        {parcelPanelVisible && (
          <aside className="flex w-96 shrink-0 flex-col overflow-y-auto border-l border-zinc-200 bg-white">
            <div className="flex shrink-0 items-center justify-end border-b border-zinc-200 px-2 py-1">
              <button
                type="button"
                onClick={() => setParcelPanelVisible(false)}
                aria-label="Hide parcel details panel"
                title="Hide parcel details panel"
                className="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700"
              >
                ✕
              </button>
            </div>
            <ParcelPanel
              parcel={parcelDetail}
              candidates={candidates}
              loading={loadingDetail}
              onSelectCandidate={handleSelectCandidate}
              onEnvelopeChange={setEnvelopeGeojson}
            />
          </aside>
        )}
        {chatVisible && (
          <aside className="w-96 shrink-0 border-l border-zinc-200 bg-white">
            <ChatPanel cadastralId={selectedParcelId} onHide={() => setChatVisible(false)} />
          </aside>
        )}
      </div>
    </div>
  );
}
