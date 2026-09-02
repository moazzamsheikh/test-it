"""M1.5 geometry-derived analysis: road frontage and neighbour distances.

Both are pure PostGIS queries against our own already-ingested parcel
geometries — no external data source needed (unlike slope, see
app/services/slope.py, which does require the external LiDAR raster).

Road frontage and the neighbour list both need to distinguish "a parcel that
is actually a public road/path" from "a parcel that is someone's land", using
ACT's own `parcel_natures.category = 'Voie de communication'` taxonomy (see
backend/app/reference_data/parcel_natures.csv). Two different subsets are
used on purpose (confirmed with the user, see DECISIONS.md):

- ROAD_NATURE_CODES (vehicular roads only) drives frontage — a parcel's
  frontage is "how much of its boundary touches a road a building could be
  accessed from", which excludes a railway, cycle path, or footpath.
- COMMUNICATION_NATURE_CODES (the full category) drives neighbour exclusion —
  a railway or footpath parcel isn't a "neighbouring property" either, even
  though it's not a road for frontage purposes.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.cadastre import Parcel
from app.schemas.parcel import NeighbourDistance

ROAD_NATURE_CODES = frozenset({5035, 5036, 5037, 5038, 5041, 5043})
COMMUNICATION_NATURE_CODES = frozenset({5035, 5036, 5037, 5038, 5039, 5040, 5041, 5043, 5044})

# Neighbours farther than this are not "neighbouring" in any useful sense;
# capped in count too so a dense Luxembourg City block can't return hundreds.
_NEIGHBOUR_RADIUS_M = 30.0
_NEIGHBOUR_LIMIT = 20


async def compute_frontage_m(session: AsyncSession, parcel_id: uuid.UUID) -> float:
    """Total length of this parcel's boundary that coincides with a
    road-nature parcel's boundary. 0.0 is a real, honest possible result (a
    landlocked parcel with no direct road access)."""
    target = aliased(Parcel)
    road = aliased(Parcel)
    shared_boundary = func.ST_Intersection(
        func.ST_Boundary(target.geom), func.ST_Boundary(road.geom)
    )
    stmt = (
        select(
            func.coalesce(
                func.sum(func.ST_Length(func.ST_CollectionExtract(shared_boundary, 2))),
                0.0,
            )
        )
        .select_from(target)
        .join(
            road,
            and_(
                road.id != target.id,
                road.nature_code.in_(ROAD_NATURE_CODES),
                func.ST_Intersects(target.geom, road.geom),
            ),
        )
        .where(target.id == parcel_id)
    )
    return float((await session.execute(stmt)).scalar_one())


async def compute_neighbours(
    session: AsyncSession, parcel_id: uuid.UUID
) -> list[NeighbourDistance]:
    """Nearby non-road parcels within _NEIGHBOUR_RADIUS_M, nearest first, with
    the true minimum boundary-to-boundary distance (0.0 for a parcel that
    actually shares a boundary edge — the majority case in a built-up area;
    a positive distance surfaces a real gap, e.g. a stream or a road strip
    that isn't itself in the road-nature exclusion set)."""
    target = aliased(Parcel)
    other = aliased(Parcel)
    distance = func.ST_Distance(target.geom, other.geom)
    stmt = (
        select(other.cadastral_id, distance.label("distance_m"))
        .select_from(target)
        .join(
            other,
            and_(
                other.id != target.id,
                other.nature_code.notin_(COMMUNICATION_NATURE_CODES) | other.nature_code.is_(None),
                func.ST_DWithin(target.geom, other.geom, _NEIGHBOUR_RADIUS_M),
            ),
        )
        .where(target.id == parcel_id)
        .order_by(distance)
        .limit(_NEIGHBOUR_LIMIT)
    )
    rows = (await session.execute(stmt)).all()
    return [
        NeighbourDistance(cadastral_id=row.cadastral_id, distance_m=float(row.distance_m))
        for row in rows
    ]


async def compute_buildable_envelope(
    session: AsyncSession, parcel_id: uuid.UUID, setback_m: float
) -> tuple[float, dict[str, object] | None]:
    """Parcel polygon minus a uniform inward setback.

    PAG/PAP setback values aren't reliably extractable yet — national/commune
    legislation ingestion (M2) hasn't started — so `setback_m` is a manual
    user input, per the brief's own explicit escape hatch for this exact gap
    (see DECISIONS.md): this is the honest answer, not a guessed number.

    Returns (area_m2, geojson) — geojson is None when the setback fully
    erodes the parcel (a real, expected outcome for a small parcel with a
    large setback, not an error).
    """
    eroded = func.ST_Buffer(Parcel.geom, -setback_m)
    stmt = select(
        func.ST_IsEmpty(eroded).label("is_empty"),
        func.ST_Area(eroded).label("area_m2"),
        func.ST_AsGeoJSON(func.ST_Transform(eroded, 4326)).label("geojson"),
    ).where(Parcel.id == parcel_id)
    row = (await session.execute(stmt)).one()
    if row.is_empty:
        return 0.0, None
    return float(row.area_m2), json.loads(row.geojson)
