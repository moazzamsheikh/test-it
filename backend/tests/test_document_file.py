"""M2 — serving a real stored graphic-document PDF (see
`app/api/v1/documents.py`), not just a metadata reference. Against the real
`pag_graphic` documents ingested by `make ingest-pag-zones`."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.enums import DocumentType
from app.models.provenance import Document

client = TestClient(app)


async def test_real_graphic_document_file_is_servable(async_db_session: AsyncSession) -> None:
    document = (
        await async_db_session.execute(
            select(Document).where(Document.document_type == DocumentType.pag_graphic).limit(1)
        )
    ).scalar_one()

    resp = client.get(f"/api/v1/documents/{document.id}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


def test_unknown_document_id_404s() -> None:
    resp = client.get(f"/api/v1/documents/{uuid.uuid4()}/file")
    assert resp.status_code == 404
