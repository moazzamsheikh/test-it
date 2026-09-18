"use client";

import { useEffect, useRef, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import Feature from "ol/Feature";
import ImageLayer from "ol/layer/Image";
import ImageWMS from "ol/source/ImageWMS";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Fill, Stroke, Style } from "ol/style";
import { transform } from "ol/proj";
import type { MapBrowserEvent } from "ol";

import { registerLuref, LUREF, WGS84 } from "@/lib/projections";
import { getOverlayLayers } from "@/lib/api";
import type { OverlayLayerInfo, ParcelDetail } from "@/lib/types";

// Real layer names, verified against a live GetMap request (not guessed) —
// see DECISIONS.md. wms.geoportail.lu/opendata/service is the endpoint that
// actually answers GetCapabilities publicly; ws.geoportail.lu (named in the
// brief) is a raw MapServer CGI requiring an undocumented `map=` parameter.
const WMS_URL = "https://wms.geoportail.lu/opendata/service";
// M1.4's thematic layers live on a THIRD, different geoportail WMS endpoint —
// found by reading the official client's own theme config, not guessed (see
// DECISIONS.md / SOURCES.md). The layer list itself comes from the backend's
// /api/v1/overlays (config-driven, not hardcoded here too).
const OVERLAY_WMS_URL = "https://wms.geoportail.lu/public_map_layers/service";
const BASE_LAYERS = [
  { id: "Basemap", label: "Topographic" },
  { id: "ortho_latest", label: "Orthophoto" },
  { id: "PCN", label: "Cadastral plan" },
] as const;
type BaseLayerId = (typeof BASE_LAYERS)[number]["id"];

// Luxembourg City centre, in LUREF — used only as the initial view.
const DEFAULT_CENTER_LUREF: [number, number] = [76500, 75300];

// Explicit resolutions (metres/pixel), not OL's default zoom levels — OL's
// built-in zoom->resolution mapping assumes a Web-Mercator-like world extent,
// which is meaningless for a small custom meter-based CRS like LUREF. Caught
// by actually loading the map: with default zoom levels, "zoom 15" resolved
// to a ~2.4m x 2.4m tile bbox — visibly wrong (grey tiles, nothing renders).
const RESOLUTIONS = [200, 100, 50, 20, 10, 5, 2, 1, 0.5, 0.25, 0.125];
const INITIAL_ZOOM_INDEX = 6; // resolution 2 m/px — a comfortable street-level view

interface Props {
  parcelDetail: ParcelDetail | null;
  flyTo: { lon: number; lat: number } | null;
  envelopeGeojson: Record<string, unknown> | null;
  onMapClick: (lon: number, lat: number) => void;
}

export default function MapView({ parcelDetail, flyTo, envelopeGeojson, onMapClick }: Props) {
  const targetRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const highlightSourceRef = useRef<VectorSource | null>(null);
  const envelopeSourceRef = useRef<VectorSource | null>(null);
  const [activeBaseLayer, setActiveBaseLayer] = useState<BaseLayerId>("Basemap");
  const [overlayLayerInfos, setOverlayLayerInfos] = useState<OverlayLayerInfo[]>([]);
  const [activeOverlayCodes, setActiveOverlayCodes] = useState<Set<string>>(new Set());
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(new Set());
  const [layersPanelVisible, setLayersPanelVisible] = useState(true);

  useEffect(() => {
    getOverlayLayers()
      .then(setOverlayLayerInfos)
      .catch(() => setOverlayLayerInfos([]));
  }, []);

  // Map initialisation — once overlay layer info has loaded, so the layer
  // order is right from the start (base layers, then overlays, then the
  // parcel highlight always on top) instead of re-inserting layers later.
  useEffect(() => {
    registerLuref();
    if (!targetRef.current || overlayLayerInfos.length === 0) return;

    function trackLoading(key: string, source: ImageWMS) {
      source.on("imageloadstart", () => {
        setLoadingKeys((prev) => new Set(prev).add(key));
      });
      const stopLoading = () => {
        setLoadingKeys((prev) => {
          if (!prev.has(key)) return prev;
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      };
      source.on("imageloadend", stopLoading);
      source.on("imageloaderror", stopLoading);
    }

    // ImageWMS (one request per view), not TileWMS (many small independent
    // tile requests): wms.geoportail.lu has no server-side tile cache and no
    // knowledge of tile boundaries when placing labels, so adjacent tiles
    // came back with visibly cut/duplicated labels and mismatched hatching —
    // a well-documented WMS issue (see DECISIONS.md), not something fixable
    // on our side since we don't control the server's mapfile config. A
    // single image per view has no seams by construction — nothing to
    // mismatch since there's only one render pass.
    const baseLayers = BASE_LAYERS.map((layer) => {
      const source = new ImageWMS({
        url: WMS_URL,
        // VERSION 1.1.1, not 1.3.0: EPSG:2169's registered axis order is
        // Northing,Easting (confirmed against the EPSG registry), and WMS
        // 1.3.0 is spec-required to honour that in BBOX — which silently
        // sent every request to the wrong real-world location (verified
        // live: an address rendered ~15km away). WMS 1.1.1's BBOX is always
        // Easting,Northing regardless of the CRS's registered axis order,
        // sidestepping the issue entirely — see DECISIONS.md.
        params: { LAYERS: layer.id, VERSION: "1.1.1", TRANSPARENT: true },
        projection: LUREF,
        ratio: 1.2,
      });
      trackLoading(`base:${layer.id}`, source);
      return new ImageLayer({
        source,
        visible: layer.id === "Basemap",
        properties: { layerId: layer.id },
      });
    });

    const overlayLayers = overlayLayerInfos.map((layer) => {
      const source = new ImageWMS({
        url: OVERLAY_WMS_URL,
        params: { LAYERS: String(layer.wms_layer_id), VERSION: "1.1.1", TRANSPARENT: true },
        projection: LUREF,
        ratio: 1.2,
      });
      trackLoading(`overlay:${layer.code}`, source);
      return new ImageLayer({
        source,
        visible: false,
        properties: { overlayCode: layer.code },
      });
    });

    const highlightSource = new VectorSource();
    highlightSourceRef.current = highlightSource;
    const highlightLayer = new VectorLayer({
      source: highlightSource,
      style: new Style({
        stroke: new Stroke({ color: "#facc15", width: 3 }),
        fill: new Fill({ color: "rgba(250, 204, 21, 0.15)" }),
      }),
    });

    // M1.5 buildable envelope — a distinct colour from the yellow parcel
    // highlight, drawn on top of it since the envelope sits inside the parcel.
    const envelopeSource = new VectorSource();
    envelopeSourceRef.current = envelopeSource;
    const envelopeLayer = new VectorLayer({
      source: envelopeSource,
      style: new Style({
        stroke: new Stroke({ color: "#16a34a", width: 2, lineDash: [6, 4] }),
        fill: new Fill({ color: "rgba(22, 163, 74, 0.2)" }),
      }),
    });

    const map = new Map({
      target: targetRef.current,
      layers: [...baseLayers, ...overlayLayers, highlightLayer, envelopeLayer],
      view: new View({
        projection: LUREF,
        center: DEFAULT_CENTER_LUREF,
        resolutions: RESOLUTIONS,
        zoom: INITIAL_ZOOM_INDEX,
      }),
    });

    map.on("click", (event: MapBrowserEvent) => {
      // The view is EPSG:2169 (LUREF); the identify API takes WGS84 — the
      // reprojection happens right here, explicitly, matching the backend's
      // own ST_Transform (see DECISIONS.md on why the datum parameters had
      // to be verified, not guessed).
      const [lon, lat] = transform(event.coordinate, LUREF, WGS84);
      onMapClick(lon, lat);
    });

    mapRef.current = map;
    return () => map.setTarget(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayLayerInfos]);

  // Base layer switching.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of map.getLayers().getArray()) {
      const layerId = layer.get("layerId") as BaseLayerId | undefined;
      if (layerId) layer.setVisible(layerId === activeBaseLayer);
    }
  }, [activeBaseLayer]);

  // Overlay layer toggling — independent checkboxes, not mutually exclusive
  // like the base layers, since several regulatory constraints can apply at once.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of map.getLayers().getArray()) {
      const overlayCode = layer.get("overlayCode") as string | undefined;
      if (overlayCode) layer.setVisible(activeOverlayCodes.has(overlayCode));
    }
  }, [activeOverlayCodes]);

  // Highlight the selected parcel's geometry.
  useEffect(() => {
    const source = highlightSourceRef.current;
    if (!source) return;
    source.clear();
    if (!parcelDetail) return;
    const geometry = new GeoJSON().readGeometry(parcelDetail.geometry_wgs84_geojson, {
      dataProjection: WGS84,
      featureProjection: LUREF,
    });
    source.addFeature(new Feature({ geometry }));
  }, [parcelDetail]);

  // M1.5 buildable envelope — cleared whenever the parent clears it (a new
  // parcel selected, or no envelope computed yet for this one).
  useEffect(() => {
    const source = envelopeSourceRef.current;
    if (!source) return;
    source.clear();
    if (!envelopeGeojson) return;
    const geometry = new GeoJSON().readGeometry(envelopeGeojson, {
      dataProjection: WGS84,
      featureProjection: LUREF,
    });
    source.addFeature(new Feature({ geometry }));
  }, [envelopeGeojson]);

  // Fly to a selected address.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !flyTo) return;
    const center = transform([flyTo.lon, flyTo.lat], WGS84, LUREF);
    // Not the max zoom index: verified live that the WMS 500s on requests at
    // the finest resolution (0.125 m/px) — this index (0.5 m/px) is close
    // enough to "zoomed into a building" without exceeding what it can serve.
    map.getView().animate({ center, zoom: 8, duration: 400 });
  }, [flyTo]);

  function toggleOverlay(code: string) {
    setActiveOverlayCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return next;
    });
  }

  return (
    <div className="relative h-full w-full">
      <div ref={targetRef} className="h-full w-full" />
      {loadingKeys.size > 0 && (
        <div className="absolute top-3 left-3 z-10 rounded-md bg-white/90 px-3 py-1.5 text-sm text-zinc-700 shadow">
          Loading map…
        </div>
      )}
      <div className="absolute top-3 right-3 z-10 flex max-h-[80vh] flex-col gap-3 overflow-auto rounded-md bg-white/90 p-2 shadow">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-zinc-500">Layers</span>
          <button
            type="button"
            onClick={() => setLayersPanelVisible((v) => !v)}
            className="rounded px-1.5 py-0.5 text-xs text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700"
          >
            {layersPanelVisible ? "Hide" : "Show"}
          </button>
        </div>
        {layersPanelVisible && (
          <>
            <div className="flex flex-col gap-1">
              {BASE_LAYERS.map((layer) => (
                <label key={layer.id} className="flex items-center gap-2 text-sm text-zinc-800">
                  <input
                    type="radio"
                    name="base-layer"
                    checked={activeBaseLayer === layer.id}
                    onChange={() => setActiveBaseLayer(layer.id)}
                  />
                  {layer.label}
                </label>
              ))}
            </div>
            {overlayLayerInfos.length > 0 && (
              <div className="flex flex-col gap-1 border-t border-zinc-200 pt-2">
                <span className="text-xs font-semibold text-zinc-500">Regulatory overlays</span>
                {overlayLayerInfos.map((layer) => (
                  <label key={layer.code} className="flex items-center gap-2 text-sm text-zinc-800">
                    <input
                      type="checkbox"
                      checked={activeOverlayCodes.has(layer.code)}
                      onChange={() => toggleOverlay(layer.code)}
                    />
                    {layer.label}
                  </label>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
