"""M1.4 regulatory overlay computation — lazy per-parcel, cached.

The external WMS (`wms.geoportail.lu/public_map_layers/service`) is slow
(~1s/request) and has no server-side cache (the same tile fetched twice takes
the same time both times — see DECISIONS.md), so results are computed once
per parcel and persisted in `parcel_overlay_results`, never re-queried for a
parcel we've already seen.

Intersection is approximated via point sampling (the parcel's centroid plus a
few points along its boundary), not a true polygon-vs-polygon test against the
overlay layer's full national geometry — there is no WFS on this service
(confirmed), so the layer's complete geometry cannot be downloaded and
intersected exactly. When a sample point *does* hit a feature, GetFeatureInfo
(INFO_FORMAT=application/json) returns that feature's real geometry, so the
overlap area is then computed exactly via shapely — what is approximate is
only whether a hit was found at all. A thin overlay strip clipping only an
unsampled stretch of the boundary could be missed. Documented, not hidden.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, TypedDict

import httpx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.cadastre import Parcel
from app.models.overlays import ParcelOverlayResult
from app.overlay_layers import OVERLAY_LAYERS, OVERLAY_WMS_URL, OverlayLayer

_SAMPLE_POINT_COUNT = 4  # plus the centroid = 5 points per layer, per parcel
_QUERY_BUFFER_M = 0.5  # tiny bbox half-width around each sample point
_MAX_CONCURRENT_REQUESTS = 8


class OverlayComputation(TypedDict):
    layer_code: str
    intersects: bool
    overlap_m2: float | None
    detail: dict[str, Any] | None
    source_url: str


def _sample_points(geom: BaseGeometry) -> list[Point]:
    """Centroid + up to _SAMPLE_POINT_COUNT points along the boundary — bounded
    regardless of how many vertices the real polygon has, so a single newly
    viewed parcel never fires an unbounded number of external requests."""
    points = [geom.centroid]
    exterior = getattr(geom, "exterior", None)
    if exterior is None:
        largest = max(geom.geoms, key=lambda g: g.area)
        exterior = largest.exterior
    coords = list(exterior.coords)[:-1]  # last point repeats the first
    if coords:
        step = max(1, len(coords) // _SAMPLE_POINT_COUNT)
        points.extend(Point(c) for c in coords[::step][:_SAMPLE_POINT_COUNT])
    return points


async def _query_point(
    client: httpx.AsyncClient, layer: OverlayLayer, point: Point, semaphore: asyncio.Semaphore
) -> dict[str, Any] | None:
    b = _QUERY_BUFFER_M
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": str(layer.wms_layer_id),
        "QUERY_LAYERS": str(layer.wms_layer_id),
        "STYLES": "",
        "CRS": "EPSG:2169",
        "BBOX": f"{point.x - b},{point.y - b},{point.x + b},{point.y + b}",
        "WIDTH": "3",
        "HEIGHT": "3",
        "I": "1",
        "J": "1",
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": "1",
    }
    async with semaphore:
        try:
            response = await client.get(OVERLAY_WMS_URL, params=params, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
    try:
        data = response.json()
    except json.JSONDecodeError:
        return None
    features = data.get("features") or []
    result: dict[str, Any] | None = features[0] if features else None
    return result


async def _compute_one_layer(
    client: httpx.AsyncClient,
    layer: OverlayLayer,
    points: list[Point],
    parcel_geom: BaseGeometry,
    semaphore: asyncio.Semaphore,
) -> OverlayComputation:
    if not layer.queryable:
        # Still a real, toggleable map layer (M1.4 asks for that too) — just
        # not one we can compute an intersects fact for via GetFeatureInfo.
        return OverlayComputation(
            layer_code=layer.code,
            intersects=False,
            overlap_m2=None,
            detail={"note": "renders on the map; no GetFeatureInfo support on this layer"},
            source_url=layer.source_url,
        )

    for point in points:
        feature = await _query_point(client, layer, point, semaphore)
        if feature is None:
            continue
        overlap_m2: float | None = None
        geom = feature.get("geometry")
        if geom:
            try:
                feature_geom = shapely_shape(geom)
                # Line/point layers (e.g. gas_network is a pipeline network,
                # not a zone) legitimately intersect without enclosing any
                # area — reporting "0.0 m²" there would read as "no real
                # overlap" when it actually means "this line runs through the
                # parcel." m² only applies to polygonal features.
                if feature_geom.geom_type in ("Polygon", "MultiPolygon"):
                    overlap_m2 = parcel_geom.intersection(feature_geom).area
            except (ValueError, AttributeError):
                overlap_m2 = None
        return OverlayComputation(
            layer_code=layer.code,
            intersects=True,
            overlap_m2=overlap_m2,
            detail=feature.get("properties"),
            source_url=layer.source_url,
        )
    return OverlayComputation(
        layer_code=layer.code,
        intersects=False,
        overlap_m2=None,
        detail=None,
        source_url=layer.source_url,
    )


async def get_or_compute_overlays(
    session: AsyncSession, parcel_id: uuid.UUID
) -> list[ParcelOverlayResult]:
    existing = (
        (
            await session.execute(
                select(ParcelOverlayResult).where(ParcelOverlayResult.parcel_id == parcel_id)
            )
        )
        .scalars()
        .all()
    )
    existing_codes = {r.layer_code for r in existing}
    missing = [layer for layer in OVERLAY_LAYERS if layer.code not in existing_codes]

    if missing:
        parcel = (await session.execute(select(Parcel).where(Parcel.id == parcel_id))).scalar_one()
        parcel_geom = to_shape(parcel.geom)
        points = _sample_points(parcel_geom)
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
        async with httpx.AsyncClient(headers={"User-Agent": settings.crawler_user_agent}) as client:
            computations = await asyncio.gather(
                *[
                    _compute_one_layer(client, layer, points, parcel_geom, semaphore)
                    for layer in missing
                ]
            )
        for computation in computations:
            stmt = insert(ParcelOverlayResult).values(parcel_id=parcel_id, **computation)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    ParcelOverlayResult.parcel_id,
                    ParcelOverlayResult.layer_code,
                ],
                set_={
                    "intersects": stmt.excluded.intersects,
                    "overlap_m2": stmt.excluded.overlap_m2,
                    "detail": stmt.excluded.detail,
                    "computed_at": func.now(),
                },
            )
            await session.execute(stmt)
        await session.commit()
        existing = (
            (
                await session.execute(
                    select(ParcelOverlayResult).where(ParcelOverlayResult.parcel_id == parcel_id)
                )
            )
            .scalars()
            .all()
        )
    return list(existing)
