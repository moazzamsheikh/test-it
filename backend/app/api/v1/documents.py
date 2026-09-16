"""Serves the real files we actually stored locally (currently: PAP QE/NQ
graphic-part PDFs — see `ingestion/ingest_pag_zones.py`). Most ingested
documents have no `storage_path` (their real content lives in `chunks.text`
instead, e.g. Legilux laws) — this endpoint is only for the kind that has no
useful text to chunk, where citing means serving the actual file."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.provenance import Document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None or document.storage_path is None:
        raise HTTPException(status_code=404, detail="no stored file for this document")

    path = Path(document.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="stored file is missing on disk")

    return FileResponse(path, media_type="application/pdf", filename=path.name)
