"""Lazy, on-demand ingestion of a real règlement grand-ducal discovered
dynamically via a per-feature Legilux link inside a live overlay result's
`detail` attributes (ZPIN's real `lien_legilux` field — see
app/overlay_layers.py's `document_url_detail_key`). Unlike the static Tier-1
documents (ingested ahead of time by ingestion/ingest_overlay_documents.py),
this can address ANY of Luxembourg's real ZPIN reserves, not just ones
manually discovered near our two target communes — the real document is
fetched the first time a real parcel hits that specific reserve, and the
result is cached on that `parcel_overlay_results` row so later parcels
hitting the same reserve never re-fetch it (mirrors the lazy-compute-once
pattern already used for the WMS overlay results themselves — see
app/services/overlays.py).

This runs inside a live API request, unlike ingest_overlay_documents.py's
batch script (which runs offline and raises loudly on any failure) — a
transient fetch/parse failure here must degrade to "no citation available"
rather than break the whole parcel-detail response for what is a bonus
citation, not core parcel data. Failures are logged, never raised.
"""

from __future__ import annotations

import hashlib
import uuid

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import AccessMethod, DocumentType, Language, LegalStatus, SourceStatus
from app.models.overlays import ParcelOverlayResult
from app.models.provenance import Chunk, Document, Source
from ingestion.legilux_extraction import eli_url_to_richtext_html_url, extract_legilux_document

logger = structlog.get_logger(__name__)

PUBLISHER = "Gouvernement du Grand-Duché de Luxembourg (Legilux)"


async def ensure_document_from_eli_link(
    session: AsyncSession, overlay_result: ParcelOverlayResult, eli_url: str, label: str
) -> uuid.UUID | None:
    if overlay_result.document_id is not None:
        return overlay_result.document_id

    document_url = eli_url_to_richtext_html_url(eli_url)

    existing = (
        await session.execute(select(Document).where(Document.source_url == document_url))
    ).scalar_one_or_none()
    if existing is not None:
        overlay_result.document_id = existing.id
        await session.commit()
        return existing.id

    try:
        async with httpx.AsyncClient(headers={"User-Agent": settings.crawler_user_agent}) as client:
            response = await client.get(document_url, timeout=15.0)
            response.raise_for_status()
        title, articles = extract_legilux_document(response.text)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "legilux_dynamic.fetch_failed",
            eli_url=eli_url,
            document_url=document_url,
            error=str(exc),
        )
        return None

    sha256 = hashlib.sha256(response.text.encode("utf-8")).hexdigest()
    source_stmt = (
        insert(Source)
        .values(
            name=f"Legilux — {label}",
            description=f"Règlement grand-ducal dynamically linked from a live {label} feature.",
            source_url=document_url,
            access_method=AccessMethod.scrape,
            publisher=PUBLISHER,
            last_fetch_at=func.now(),
            last_success_at=func.now(),
            last_status=SourceStatus.ok,
        )
        .on_conflict_do_update(
            index_elements=[Source.name],
            set_={
                "last_fetch_at": func.now(),
                "last_success_at": func.now(),
                "last_status": SourceStatus.ok,
            },
        )
        .returning(Source.id)
    )
    source_id = (await session.execute(source_stmt)).scalar_one()

    document = Document(
        source_id=source_id,
        source_url=document_url,
        title=title or label,
        publisher=PUBLISHER,
        sha256=sha256,
        language=Language.fr,
        legal_status=LegalStatus.in_force,
        document_type=DocumentType.reglement_grand_ducal,
    )
    session.add(document)
    await session.flush()
    await session.execute(
        update(Source)
        .where(Source.id == source_id)
        .values(documents_ingested=Source.documents_ingested + 1)
    )

    for ordinal, article in enumerate(articles):
        session.add(
            Chunk(
                document_id=document.id,
                ordinal=ordinal,
                article_ref=article.article_ref,
                text=article.text,
                document_type=DocumentType.reglement_grand_ducal,
                language=Language.fr,
                legal_status=LegalStatus.in_force,
            )
        )

    overlay_result.document_id = document.id
    await session.commit()
    logger.info(
        "legilux_dynamic.ingested",
        eli_url=eli_url,
        document_id=str(document.id),
        articles=len(articles),
    )
    return document.id
