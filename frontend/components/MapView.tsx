"use client";

import { useEffect, useRef, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import Feature from "ol/Feature";
import TileLayer from "ol/layer/Tile";
import TileWMS from "ol/source/TileWMS";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Fill, Stroke, Style } from "ol/style";
import { transform } from "ol/proj";
import type { MapBrowserEvent } from "ol";

import { registerLuref, LUREF, WGS84 } from "@/lib/projections";
import type { ParcelDetail } from "@/lib/types";

// Real layer names, verified against a live GetMap request (not guessed) —
// see DECISIONS.md. wms.geoportail.lu/opendata/service is the endpoint that
// actually answers GetCapabilities publicly; ws.geoportail.lu (named in the
// brief) is a raw MapServer CGI requiring an undocumented `map=` parameter.
const WMS_URL = "https://wms.geoportail.lu/opendata/service";
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
  onMapClick: (lon: number, lat: number) => void;
}

export default function MapView({ parcelDetail, flyTo, onMapClick }: Props) {
  const targetRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const highlightSourceRef = useRef<VectorSource | null>(null);
  const [activeBaseLayer, setActiveBaseLayer] = useState<BaseLayerId>("Basemap");

  // Map initialisation — once.
  useEffect(() => {
    registerLuref();
    if (!targetRef.current) return;

    const baseLayers = BASE_LAYERS.map(
      (layer) =>
        new TileLayer({
          source: new TileWMS({
            url: WMS_URL,
            params: { LAYERS: layer.id, VERSION: "1.3.0", TRANSPARENT: true },
            projection: LUREF,
          }),
          visible: layer.id === "Basemap",
          properties: { layerId: layer.id },
        }),
    );

    const highlightSource = new VectorSource();
    highlightSourceRef.current = highlightSource;
    const highlightLayer = new VectorLayer({
      source: highlightSource,
      style: new Style({
        stroke: new Stroke({ color: "#facc15", width: 3 }),
        fill: new Fill({ color: "rgba(250, 204, 21, 0.15)" }),
      }),
    });

    const map = new Map({
      target: targetRef.current,
      layers: [...baseLayers, highlightLayer],
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
  }, []);

  // Base layer switching.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of map.getLayers().getArray()) {
      const layerId = layer.get("layerId") as BaseLayerId | undefined;
      if (layerId) layer.setVisible(layerId === activeBaseLayer);
    }
  }, [activeBaseLayer]);

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

  return (
    <div className="relative h-full w-full">
      <div ref={targetRef} className="h-full w-full" />
      <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 rounded-md bg-white/90 p-2 shadow">
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
    </div>
  );
}
