/**
 * Registers EPSG:2169 (LUREF / Luxembourg 1930 Gauss) with proj4 so OpenLayers
 * can use it as the map's working projection — source geodata (PCN, BD-Adresses)
 * is natively 2169; only browser input (geolocation, WGS84 map libraries) is
 * EPSG:4326.
 *
 * The towgs84 datum-shift parameters below are copied verbatim from
 * PostGIS's own `spatial_ref_sys.proj4text` for SRID 2169 (verified via
 * `SELECT proj4text FROM spatial_ref_sys WHERE srid = 2169`), NOT guessed —
 * a first attempt with different (also plausible-looking) parameters was off
 * by 108 metres against the backend's PostGIS/PROJ transform for the same
 * known coordinate pair used in the backend's own reprojection proof
 * (see DECISIONS.md). With these parameters, proj4 agrees with PostGIS to
 * ~1.5mm — verified with `node -e` before this file was used anywhere.
 */
import proj4 from "proj4";
import { register } from "ol/proj/proj4";
import { get as getProjection } from "ol/proj";

const LUREF_PROJ4_DEF =
  "+proj=tmerc +lat_0=49.83333333333334 +lon_0=6.166666666666667 +k=1 " +
  "+x_0=80000 +y_0=100000 +ellps=intl " +
  "+towgs84=-189.6806,18.3463,-42.7695,-0.33746,-3.09264,2.53861,0.4598 " +
  "+units=m +no_defs";

let registered = false;

export function registerLuref(): void {
  if (registered) return;
  proj4.defs("EPSG:2169", LUREF_PROJ4_DEF);
  register(proj4);
  const luref = getProjection("EPSG:2169");
  if (luref) {
    // Luxembourg's full extent in LUREF, roughly — used for view constraints.
    luref.setExtent([49000, 61000, 108000, 140000]);
  }
  registered = true;
}

export const LUREF = "EPSG:2169";
export const WGS84 = "EPSG:4326";
