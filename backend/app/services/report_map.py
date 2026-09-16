"""M4.2 — the PDF cover page's "map extract showing the parcel highlighted
in context." No server-side map renderer exists elsewhere in this project
(the map UI is client-side OpenLayers) — this fetches a real basemap tile
from the same public WMS the frontend already uses (`wms.geoportail.lu/
opendata/service`, layer `Basemap` — see `frontend/components/MapView.tsx`),
then draws the parcel's own real boundary on top via Pillow, reprojecting
its geometry into the fetched image's pixel space.

Determinism caveat, honestly noted rather than hidden: the report JSON and
the PDF's text content are byte-deterministic for a fixed parcel + corpus
state, but this one embedded image is a real government basemap tile
fetched over the network — stable in practice (base cartography changes
rarely) but not something this project controls or can guarantee bit-for-bit
forever, unlike everything else in the PDF.

Cached to disk per parcel (same `data/cache` discipline as
`ingestion/download_cache.py`) — without this, every PDF request (and every
test run) would re-hit a public government WMS, which is exactly the
"cache aggressively, don't hammer public servers" principle this project
already applies everywhere else (see `app/services/overlays.py`'s own
per-parcel DB cache).
"""

from __future__ import annotations

import json
import uuid
from io import BytesIO

import httpx
from PIL import Image, ImageDraw
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from ingestion.config import CACHE_DIR

_WMS_URL = "https://wms.geoportail.lu/opendata/service"
_BASE_LAYER = "Basemap"
_PAD_M = 25.0
_MAX_DIM_PX = 900
_MIN_DIM_PX = 400
_OUTLINE_COLOR = (220, 30, 30, 255)
_MAP_CACHE_DIR = CACHE_DIR / "parcel_maps"
_OUTLINE_WIDTH_PX = 5


async def _fetch_parcel_bbox_and_rings(
    session: AsyncSession, parcel_id: uuid.UUID, user_agent: str
) -> tuple[tuple[float, float, float, float], list[list[tuple[float, float]]]] | None:
    row = (
        await session.execute(
            select(
                func.ST_XMin(func.ST_Transform(Parcel.geom, 3857)),
                func.ST_YMin(func.ST_Transform(Parcel.geom, 3857)),
                func.ST_XMax(func.ST_Transform(Parcel.geom, 3857)),
                func.ST_YMax(func.ST_Transform(Parcel.geom, 3857)),
                func.ST_AsGeoJSON(func.ST_Transform(Parcel.geom, 3857)),
            ).where(Parcel.id == parcel_id)
        )
    ).one_or_none()
    if row is None:
        return None
    xmin, ymin, xmax, ymax, geojson_text = row
    geojson = json.loads(geojson_text)
    coords = geojson["coordinates"]
    # MultiPolygon: [ [ [ [x,y], ... ] (exterior ring), [holes...] ], ... polygons ]
    rings: list[list[tuple[float, float]]] = []
    for polygon in coords:
        exterior = polygon[0]
        rings.append([(pt[0], pt[1]) for pt in exterior])
    return (xmin, ymin, xmax, ymax), rings


def _padded_bbox_and_size(
    bbox: tuple[float, float, float, float],
) -> tuple[tuple[float, float, float, float], tuple[int, int]]:
    xmin, ymin, xmax, ymax = bbox
    xmin, ymin, xmax, ymax = xmin - _PAD_M, ymin - _PAD_M, xmax + _PAD_M, ymax + _PAD_M
    width_m, height_m = xmax - xmin, ymax - ymin
    if width_m <= 0 or height_m <= 0:
        width_m = height_m = max(width_m, height_m, 1.0)
    aspect = width_m / height_m
    if aspect >= 1:
        width_px = _MAX_DIM_PX
        height_px = max(_MIN_DIM_PX, round(_MAX_DIM_PX / aspect))
    else:
        height_px = _MAX_DIM_PX
        width_px = max(_MIN_DIM_PX, round(_MAX_DIM_PX * aspect))
    return (xmin, ymin, xmax, ymax), (width_px, height_px)


def _to_pixels(
    rings: list[list[tuple[float, float]]],
    bbox: tuple[float, float, float, float],
    size: tuple[int, int],
) -> list[list[tuple[float, float]]]:
    xmin, ymin, xmax, ymax = bbox
    width_px, height_px = size
    pixel_rings = []
    for ring in rings:
        pixel_rings.append(
            [
                (
                    (x - xmin) / (xmax - xmin) * width_px,
                    height_px - (y - ymin) / (ymax - ymin) * height_px,
                )
                for x, y in ring
            ]
        )
    return pixel_rings


async def render_parcel_map_extract(
    session: AsyncSession, parcel_id: uuid.UUID, user_agent: str
) -> bytes | None:
    """Returns a PNG with the real parcel boundary highlighted over a real
    basemap tile, or None if the parcel's geometry couldn't be resolved (an
    honest gap surfaced to the caller, not a placeholder image). Cached to
    disk per parcel — see module docstring."""
    cache_path = _MAP_CACHE_DIR / f"{parcel_id}.png"
    if cache_path.exists():
        return cache_path.read_bytes()

    result = await _fetch_parcel_bbox_and_rings(session, parcel_id, user_agent)
    if result is None:
        return None
    raw_bbox, rings = result
    bbox, size = _padded_bbox_and_size(raw_bbox)

    response = httpx.get(
        _WMS_URL,
        params={
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": _BASE_LAYER,
            "STYLES": "",
            "CRS": "EPSG:3857",
            "BBOX": ",".join(str(v) for v in bbox),
            "WIDTH": str(size[0]),
            "HEIGHT": str(size[1]),
            "FORMAT": "image/png",
        },
        headers={"User-Agent": user_agent},
        timeout=30,
    )
    response.raise_for_status()

    image = Image.open(BytesIO(response.content)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    for ring in _to_pixels(rings, bbox, size):
        draw.polygon(ring, outline=_OUTLINE_COLOR, width=_OUTLINE_WIDTH_PX)

    out = BytesIO()
    image.convert("RGB").save(out, format="PNG")
    png_bytes = out.getvalue()

    _MAP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(png_bytes)
    return png_bytes
