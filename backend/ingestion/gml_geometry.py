"""Parses the specific INTERLIS/GML polygon structure used in ACT's real PAG
open-data exports (see DECISIONS.md) — verified live against real Luxembourg
City and Wiltz PAG GML files. Not a general-purpose GML reader: written
against the one structure this project actually ingests (a single
gml:Polygon per feature, linear-interpolation LineStringSegments, optional
interior rings for holes). An unexpected shape (e.g. a MultiSurface) raises
rather than silently producing a wrong geometry — no GML feature type has
been ingested here without seeing it in real data first.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from shapely.geometry import MultiPolygon, Polygon

_GML = "{http://www.opengis.net/gml/3.2}"


def _parse_pos_list(text: str) -> list[tuple[float, float]]:
    values = [float(v) for v in text.split()]
    if len(values) % 2 != 0:
        raise ValueError(f"posList has an odd number of values: {len(values)}")
    return list(zip(values[0::2], values[1::2], strict=True))


def _parse_ring(ring_el: ET.Element) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    curve_members = ring_el.findall(f"{_GML}curveMember")
    if not curve_members:
        raise ValueError("gml:Ring has no gml:curveMember — unexpected GML shape")
    for curve_member in curve_members:
        curve = curve_member.find(f"{_GML}Curve")
        if curve is None:
            raise ValueError("gml:curveMember has no gml:Curve — unexpected GML shape")
        segments = curve.find(f"{_GML}segments")
        if segments is None:
            raise ValueError("gml:Curve has no gml:segments — unexpected GML shape")
        for seg in segments.findall(f"{_GML}LineStringSegment"):
            interpolation = seg.get("interpolation")
            if interpolation != "linear":
                raise ValueError(f"unsupported interpolation: {interpolation!r}")
            pos_list_el = seg.find(f"{_GML}posList")
            if pos_list_el is None or pos_list_el.text is None:
                raise ValueError("gml:LineStringSegment has no gml:posList")
            segment_coords = _parse_pos_list(pos_list_el.text)
            # Consecutive segments share their join point — drop the duplicate.
            if coords and segment_coords and coords[-1] == segment_coords[0]:
                coords.extend(segment_coords[1:])
            else:
                coords.extend(segment_coords)
    return coords


def parse_gml_polygon(geometrie_el: ET.Element) -> MultiPolygon:
    """`geometrie_el` is a <GEOMETRIE> element wrapping exactly one gml:Polygon
    (verified against real data — no gml:MultiSurface seen; raises if one
    turns up rather than guessing how to handle it)."""
    polygon_el = geometrie_el.find(f"{_GML}Polygon")
    if polygon_el is None:
        raise ValueError(
            f"expected a single gml:Polygon under GEOMETRIE, got: "
            f"{[c.tag for c in geometrie_el]}"
        )
    exterior_ring_el = polygon_el.find(f"{_GML}exterior/{_GML}Ring")
    if exterior_ring_el is None:
        raise ValueError("gml:Polygon has no gml:exterior/gml:Ring")
    exterior = _parse_ring(exterior_ring_el)
    holes = [
        _parse_ring(interior_ring_el)
        for interior_ring_el in polygon_el.findall(f"{_GML}interior/{_GML}Ring")
    ]
    return MultiPolygon([Polygon(exterior, holes)])
