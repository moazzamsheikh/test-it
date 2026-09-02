"""M1.5 slope-from-LiDAR response schema."""

from __future__ import annotations

from pydantic import BaseModel


class SlopeResult(BaseModel):
    # All null together = genuinely not covered by the raster / no valid
    # pixels found (see app/services/slope.py) — never a fabricated zero.
    avg_slope_pct: float | None
    max_slope_pct: float | None
    min_elevation_m: float | None
    max_elevation_m: float | None
    sample_pixel_count: int
    source_url: str
