"""M2.1 — the observability requirement: a status view per source (last
successful fetch, documents ingested, failures, staleness), not just a raw
DB table only visible via psql. Every field here already exists on the
`Source` model (`documents.py`'s docstring: "Drives incremental fetch + the
status dashboard") — this is a read-only projection, not new tracking."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SourceStatusInfo(BaseModel):
    id: uuid.UUID
    name: str
    source_url: str
    publisher: str | None
    access_method: str
    last_fetch_at: datetime | None
    last_success_at: datetime | None
    last_status: str
    last_error: str | None
    failure_count: int
    documents_ingested: int
    updated_at: datetime
