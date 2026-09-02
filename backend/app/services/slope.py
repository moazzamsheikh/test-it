"""M1.5 slope-from-LiDAR computation — lazy per-parcel, cached.

Source: ACT's real, open (CC0) 2024 LiDAR-derived terrain model
(data.public.lu, BD-L-Lidar2024) — a single country-wide Cloud-Optimized
GeoTIFF (COG) at 50cm resolution, verified live to already be in EPSG:2169
(matching our parcel geometries, no reprojection needed). The file itself is
~40GB and not something to download; a COG supports HTTP range requests, so
GDAL's `/vsicurl/` driver pulls only the pixel window over a given parcel's
bounding box (a few MB, a few seconds) — see DECISIONS.md for the research
trail and the verified live windowed-read numbers.

Results are cached per parcel in `parcel_slope_results`, the same lazy-
compute-once pattern as M1.4 overlays: paid once per parcel, never repeated.
A parcel outside the raster's extent, or entirely covered by nodata pixels,
gets an honest all-null cached result (sample_pixel_count == 0) rather than a
fabricated zero — and that "no data" result is itself cached, so we don't
re-attempt the network read for a parcel we already know isn't covered.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

# Must be set before the first rasterio.open() of the /vsicurl/ URL below:
# avoids GDAL probing for sidecar files (.aux.xml, .ovr, a directory listing)
# that don't exist and aren't supported over plain HTTP anyway — each such
# probe is otherwise its own failed request against a public government file.
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

import numpy as np
import rasterio
from geoalchemy2.shape import to_shape
from rasterio.io import DatasetReader
from rasterio.mask import mask as rio_mask
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Parcel
from app.models.slope import ParcelSlopeResult

LIDAR_MNT_URL = (
    "https://download.data.public.lu/resources/"
    "bd-l-lidar2024-releve-3d-du-territoire-luxembourgeois/"
    "20241223-093912/MNT_Lidar2024.tif"
)
_VSICURL_URL = f"/vsicurl/{LIDAR_MNT_URL}"
_PIXEL_SIZE_M = 0.5

# A single process-wide dataset handle (opening costs ~8s — GDAL fetching the
# COG's own header/overview structure over HTTP — reused across requests so
# only the windowed pixel read is paid per parcel) guarded by one lock: GDAL
# dataset handles aren't safe for concurrent reads from multiple threads, and
# with per-parcel caching there's no throughput need to parallelise this.
_dataset: DatasetReader | None = None
_lock = asyncio.Lock()


def _compute_slope_sync(dataset: DatasetReader, geom: BaseGeometry) -> dict[str, Any] | None:
    try:
        out_image, _ = rio_mask(dataset, [geom], crop=True, nodata=np.nan, filled=True)
    except ValueError:
        # Real, documented rasterio behaviour when the shape doesn't overlap
        # the raster at all — an honest "not covered", not an error to hide.
        return None
    data = out_image[0]
    if data.shape[0] < 2 or data.shape[1] < 2:
        return None  # too slender to take a gradient
    sample_pixel_count = int(np.sum(~np.isnan(data)))
    if sample_pixel_count == 0:
        return None
    gy, gx = np.gradient(data, _PIXEL_SIZE_M, _PIXEL_SIZE_M)
    slope_ratio = np.sqrt(gx**2 + gy**2)
    return {
        "avg_slope_pct": float(np.nanmean(slope_ratio) * 100),
        "max_slope_pct": float(np.nanmax(slope_ratio) * 100),
        "min_elevation_m": float(np.nanmin(data)),
        "max_elevation_m": float(np.nanmax(data)),
        "sample_pixel_count": sample_pixel_count,
    }


async def get_or_compute_slope(session: AsyncSession, parcel_id: uuid.UUID) -> ParcelSlopeResult:
    existing = (
        await session.execute(
            select(ParcelSlopeResult).where(ParcelSlopeResult.parcel_id == parcel_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    parcel = (await session.execute(select(Parcel).where(Parcel.id == parcel_id))).scalar_one()
    geom = to_shape(parcel.geom)

    async with _lock:
        global _dataset
        if _dataset is None:
            _dataset = await asyncio.to_thread(rasterio.open, _VSICURL_URL)
        computed = await asyncio.to_thread(_compute_slope_sync, _dataset, geom)

    values: dict[str, Any] = computed or {
        "avg_slope_pct": None,
        "max_slope_pct": None,
        "min_elevation_m": None,
        "max_elevation_m": None,
        "sample_pixel_count": 0,
    }
    stmt = insert(ParcelSlopeResult).values(parcel_id=parcel_id, source_url=LIDAR_MNT_URL, **values)
    stmt = stmt.on_conflict_do_nothing(index_elements=[ParcelSlopeResult.parcel_id])
    await session.execute(stmt)
    await session.commit()
    return (
        await session.execute(
            select(ParcelSlopeResult).where(ParcelSlopeResult.parcel_id == parcel_id)
        )
    ).scalar_one()
