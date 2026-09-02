"""M1.4 overlay layer config endpoint — lets the frontend render the layer
switcher and WMS requests without hardcoding the (config-driven) layer list."""

from __future__ import annotations

from fastapi import APIRouter

from app.overlay_layers import OVERLAY_LAYERS
from app.schemas.overlay import OverlayLayerInfo

router = APIRouter(prefix="/overlays", tags=["overlays"])


@router.get("", response_model=list[OverlayLayerInfo])
async def list_overlay_layers() -> list[OverlayLayerInfo]:
    return [
        OverlayLayerInfo(
            code=layer.code,
            label=layer.label,
            category=layer.category,
            wms_layer_id=layer.wms_layer_id,
            queryable=layer.queryable,
            source_url=layer.source_url,
        )
        for layer in OVERLAY_LAYERS
    ]
