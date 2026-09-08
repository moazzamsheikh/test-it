"""Ingest the real règlements grand-ducaux that govern the M1.4 overlay
layers which have a single applicable document (see `OverlayLayer.document_url`
in app/overlay_layers.py — Tier 1 of the post-M1 overlay-document gap: see
DECISIONS.md). Config-driven, same reason M1.4's WMS layers are: one entry
per layer here, not one hardcoded ingestion function per document.

Uses the Legilux "richtext" HTML export format (ingestion/legilux_extraction.py),
verified reusable across every RGD this project has needed so far — one real
`Art. N` article per chunk, matching the project's existing per-article
chunking (PAG zones, M5's procedure).

Run with: make ingest-overlay-documents
"""

from __future__ import annotations

import hashlib

import structlog
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.enums import AccessMethod, DocumentType, Language, LegalStatus, SourceStatus
from app.models.provenance import Chunk, Document, Source
from app.overlay_layers import OVERLAY_LAYERS, OverlayLayer
from ingestion.download_cache import download_cached
from ingestion.legilux_extraction import extract_legilux_document

logger = structlog.get_logger(__name__)

PUBLISHER = "Gouvernement du Grand-Duché de Luxembourg (Legilux)"


def _cache_filename(layer: OverlayLayer) -> str:
    return f"legilux_{layer.code}.html"


def _ingest_one(session: Session, layer: OverlayLayer) -> Document | None:
    if layer.document_url is None:
        return None

    html_path = download_cached(layer.document_url, _cache_filename(layer))
    html = html_path.read_text(encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    title, articles = extract_legilux_document(html)

    source_name = f"Legilux — {layer.label}"
    source_stmt = (
        insert(Source)
        .values(
            name=source_name,
            description=f"Règlement grand-ducal governing the {layer.label} overlay layer.",
            source_url=layer.document_url,
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
    source_id = session.execute(source_stmt).scalar_one()

    existing = session.execute(
        select(Document).where(
            Document.source_url == layer.document_url,
            Document.sha256 == sha256,
        )
    ).scalar_one_or_none()
    if existing is not None:
        logger.info(
            "ingest.overlay_document.unchanged", layer=layer.code, document_id=str(existing.id)
        )
        return existing

    document = Document(
        source_id=source_id,
        source_url=layer.document_url,
        title=title or layer.label,
        publisher=PUBLISHER,
        sha256=sha256,
        language=Language.fr,
        legal_status=LegalStatus.in_force,
        document_type=DocumentType.reglement_grand_ducal,
    )
    session.add(document)
    session.flush()
    session.execute(
        update(Source)
        .where(Source.id == source_id)
        .values(documents_ingested=Source.documents_ingested + 1)
    )

    session.execute(delete(Chunk).where(Chunk.document_id == document.id))
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

    logger.info(
        "ingest.overlay_document.new_document",
        layer=layer.code,
        document_id=str(document.id),
        articles=len(articles),
    )
    return document


def ingest(session: Session) -> list[Document]:
    documents = []
    for layer in OVERLAY_LAYERS:
        document = _ingest_one(session, layer)
        if document is not None:
            documents.append(document)
    return documents


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        documents = ingest(session)
        session.commit()
        count = len(documents)
    logger.info("ingest.overlay_documents.complete", documents=count)


if __name__ == "__main__":
    main()
