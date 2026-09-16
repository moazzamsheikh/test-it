"""M2.4 bonus — real SPARQL-derived amendment-chain windows, one per
Legilux consolidation (or per as-published "jo" text where no consolidation
exists), for the national legislation corpus."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class LegislationVersionInfo(BaseModel):
    work_eli: str
    version_eli: str
    expression_url: str
    date_applicability: date
    date_end_applicability: date | None
    in_force_status: str | None
    document_id: uuid.UUID | None
