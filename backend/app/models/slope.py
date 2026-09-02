"""M1.5 slope-from-LiDAR results — computed lazily per parcel and cached here
(see DECISIONS.md: the source is a real, open 40GB COG on data.public.lu; a
windowed HTTP range-read is a few seconds, so it's paid once per parcel and
never repeated).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ParcelSlopeResult(Base):
    __tablename__ = "parcel_slope_results"

    parcel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), primary_key=True
    )
    # All nullable together: a parcel outside the raster's extent, or entirely
    # covered by nodata pixels, is an honest "no data" result, not a
    # fabricated zero — sample_pixel_count == 0 is what distinguishes it from
    # a real, computed (if small) slope.
    avg_slope_pct: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    max_slope_pct: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    min_elevation_m: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    max_elevation_m: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    sample_pixel_count: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
