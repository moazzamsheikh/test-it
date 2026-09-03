"""Guards against silently regressing the WMS axis-order bug (see DECISIONS.md):
EPSG:2169's registered axis order is Northing,Easting, so a WMS 1.3.0 request
built with our normal (Easting,Northing) BBOX queries a location up to ~15km
away from the real point — verified live against the real server, not just
theorised. WMS 1.1.1 sidesteps this since its BBOX is always Easting,Northing
regardless of the CRS's registered axis order. This test only needs to prove
the param shape is right; the live behaviour was verified by hand.
"""

from __future__ import annotations

from shapely.geometry import Point

from app.overlay_layers import OVERLAY_LAYERS
from app.services.overlays import _build_getfeatureinfo_params


def test_getfeatureinfo_uses_wms_1_1_1_not_1_3_0() -> None:
    params = _build_getfeatureinfo_params(OVERLAY_LAYERS[0], Point(77057.665, 75230.965))

    assert params["VERSION"] == "1.1.1"
    assert params["SRS"] == "EPSG:2169"
    assert "CRS" not in params  # the 1.3.0 param name — must not reappear
    assert params["X"] == "1"
    assert params["Y"] == "1"
    assert "I" not in params and "J" not in params  # the 1.3.0 pixel-coord names


def test_getfeatureinfo_bbox_is_easting_northing_order() -> None:
    point = Point(77057.665, 75230.965)
    params = _build_getfeatureinfo_params(OVERLAY_LAYERS[0], point)

    minx, miny, maxx, maxy = (float(v) for v in params["BBOX"].split(","))
    assert minx < point.x < maxx
    assert miny < point.y < maxy
