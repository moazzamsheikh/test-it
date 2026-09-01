"""Shapefile record reader: pyshp + shapely, no GDAL (see DECISIONS.md).

Pure Python — keeps `make ingest` working with just `pip install -e .[dev]`,
no system package manager step, matching the README's clean-machine promise.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import shapefile
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry


def iter_filtered(
    shp_path: Path,
    predicate: Callable[[dict[str, Any]], bool],
    encoding: str = "utf-8",
) -> Iterator[tuple[dict[str, Any], BaseGeometry]]:
    """Yield (attributes, geometry) for records matching `predicate`.

    Two-pass by design: `iterRecords()` reads only the .dbf attribute table
    (cheap), and geometry is parsed from the .shp file only for records that
    pass the filter. PARCELLES has 717k national records; we only need the
    few thousand belonging to our two target communes, so skipping shapely
    construction for the rest matters for runtime, not just correctness.

    `encoding` is read from the sibling .cpg sidecar in practice (verified
    "UTF-8" for PCN — a naive Latin-1 default mojibakes accented LIEUDIT
    values, e.g. "Allée" -> "AllÃ©e"), passed explicitly rather than relying on
    pyshp's auto-detection so the assumption is visible in code, not implicit.
    """
    with shapefile.Reader(str(shp_path), encoding=encoding) as reader:
        field_names = [f[0] for f in reader.fields[1:]]  # [0] is the deletion flag
        for idx, record in enumerate(reader.iterRecords()):
            attrs = dict(zip(field_names, record, strict=True))
            if not predicate(attrs):
                continue
            yield attrs, shape(reader.shape(idx).__geo_interface__)


def as_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    """Coerce a Polygon to MultiPolygon — PCN ships single-part records as
    Polygon, but our schema declares MULTIPOLYGON columns for consistency
    (a parcel could legitimately be multi-part after a subdivision)."""
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    raise TypeError(f"Expected Polygon or MultiPolygon, got {geom.geom_type}")
