"""M1.4 regulatory overlay results — computed lazily per parcel and cached here
(see DECISIONS.md: the external WMS is slow with no server-side cache, so we
compute once per parcel and never re-query it for a parcel we've already seen).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ParcelOverlayResult(Base):
    __tablename__ = "parcel_overlay_results"
    __table_args__ = (UniqueConstraint("parcel_id", "layer_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parcel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), index=True
    )
    layer_code: Mapped[str] = mapped_column(Text)
    intersects: Mapped[bool] = mapped_column()
    # Real intersection area, computed from the actual geometry GetFeatureInfo
    # returned — null when intersects is False, or when a hit was found but no
    # geometry came back (some layers don't return one — see DECISIONS.md).
    overlap_m2: Mapped[float | None] = mapped_column(Numeric(asdecimal=False), default=None)
    # Raw GetFeatureInfo properties for the intersecting feature, if any —
    # whatever attributes that specific layer happens to carry.
    detail: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    source_url: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
