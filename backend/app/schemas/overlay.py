"""M1.4 overlay layer config, exposed to the frontend so it doesn't duplicate
the layer list — one source of truth for "what layers exist", same principle
as the layers themselves being config-driven rather than hardcoded."""

from __future__ import annotations

from pydantic import BaseModel


class OverlayLayerInfo(BaseModel):
    code: str
    label: str
    category: str
    wms_layer_id: int
    queryable: bool
    source_url: str
