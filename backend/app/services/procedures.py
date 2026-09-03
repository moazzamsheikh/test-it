"""M5 procedure lookups — a plain read of the one real document ingested by
`ingestion/ingest_procedure_building_permit.py` (see DECISIONS.md). No
compute/caching needed here, unlike overlays/slope: this is just ordered
rows already sitting in Postgres.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DocumentType
from app.models.provenance import Chunk, Document
from app.schemas.procedure import LegalReference, ProcedureDetail, ProcedureSection


async def get_building_permit_procedure(session: AsyncSession) -> ProcedureDetail | None:
    # "Latest procedure_guide document" is unambiguous only because exactly
    # one is ingested today. Adding a second real procedure later needs a
    # real disambiguator (e.g. filtering on source_url) — not guessed now.
    document = (
        await session.execute(
            select(Document)
            .where(Document.document_type == DocumentType.procedure_guide)
            .order_by(Document.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if document is None:
        return None

    chunks = (
        (
            await session.execute(
                select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.ordinal)
            )
        )
        .scalars()
        .all()
    )

    sections = [
        ProcedureSection(heading=c.heading or "", text=c.text)
        for c in chunks
        if c.heading != "Base légale"
    ]
    legal_references = [
        LegalReference(label=c.article_ref or "", url=c.text)
        for c in chunks
        if c.heading == "Base légale"
    ]

    return ProcedureDetail(
        title=document.title or "",
        source_url=document.source_url,
        publisher=document.publisher or "",
        document_date=document.document_date,
        sections=sections,
        legal_references=legal_references,
    )
