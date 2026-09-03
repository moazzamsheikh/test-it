"""Ingest the real building-permit procedure page from guichet.public.lu (M5,
scoped deliberately small — see DECISIONS.md: this is ONE real, hand-picked
procedure ingested through the existing sources/documents/chunks provenance
schema, not the full M2 legislation crawler).

Run with: make ingest-procedures
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime

import structlog
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.enums import AccessMethod, DocumentType, Language, LegalStatus, SourceStatus
from app.models.provenance import Chunk, Document, Source
from ingestion.download_cache import download_cached
from ingestion.procedure_extraction import extract_procedure

PROCEDURE_URL = (
    "https://guichet.public.lu/fr/citoyens/logement/construction-renovation-transformation/"
    "travaux/autorisation-batir.html"
)
SOURCE_NAME = "Guichet.lu — Autorisation de bâtir"
PUBLISHER = "Guichet.lu (Gouvernement du Grand-Duché de Luxembourg)"

logger = structlog.get_logger(__name__)


def _parse_page_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    return datetime.strptime(raw, "%d.%m.%Y").date()


def ingest(session: Session) -> Document:
    html_path = download_cached(PROCEDURE_URL, "guichet_autorisation_batir.html")
    html = html_path.read_text(encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    extracted = extract_procedure(html)

    source_stmt = (
        insert(Source)
        .values(
            name=SOURCE_NAME,
            description="Real-estate/construction procedure guide for Luxembourg citizens.",
            source_url=PROCEDURE_URL,
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
            Document.source_url == PROCEDURE_URL,
            Document.sha256 == sha256,
        )
    ).scalar_one_or_none()
    if existing is not None:
        logger.info("ingest.procedure.unchanged", document_id=str(existing.id))
        return existing

    document = Document(
        source_id=source_id,
        source_url=PROCEDURE_URL,
        title=extracted.title,
        publisher=PUBLISHER,
        document_date=_parse_page_date(extracted.document_date_str),
        sha256=sha256,
        language=Language.fr,
        legal_status=LegalStatus.unknown,  # a procedure guide, not itself an act of law
        document_type=DocumentType.procedure_guide,
    )
    session.add(document)
    session.flush()
    session.execute(
        update(Source)
        .where(Source.id == source_id)
        .values(documents_ingested=Source.documents_ingested + 1)
    )

    session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    ordinal = 0
    for section in extracted.sections:
        session.add(
            Chunk(
                document_id=document.id,
                ordinal=ordinal,
                heading=section.heading,
                text=section.text,
                document_type=DocumentType.procedure_guide,
                language=Language.fr,
                legal_status=LegalStatus.unknown,
                document_date=document.document_date,
            )
        )
        ordinal += 1
    for ref in extracted.legal_references:
        session.add(
            Chunk(
                document_id=document.id,
                ordinal=ordinal,
                heading="Base légale",
                article_ref=ref.label,
                text=ref.url,
                document_type=DocumentType.procedure_guide,
                language=Language.fr,
                legal_status=LegalStatus.unknown,
                document_date=document.document_date,
            )
        )
        ordinal += 1

    logger.info(
        "ingest.procedure.new_document",
        document_id=str(document.id),
        sections=len(extracted.sections),
        legal_references=len(extracted.legal_references),
    )
    return document


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        document = ingest(session)
        session.commit()
        document_id = document.id
    logger.info("ingest.procedure.complete", document_id=str(document_id))


if __name__ == "__main__":
    main()
