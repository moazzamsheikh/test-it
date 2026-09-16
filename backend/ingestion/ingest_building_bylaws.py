"""M2.3/M2.4 — building bylaws (règlement sur les bâtisses, les voies
publiques et les sites) for the 8 deep-ingestion communes. The brief
itself says "no central repository exists — commune website only", so
each real PDF URL below was found by hand, one commune at a time, and
verified to actually fetch and extract real text before being added here
(see DECISIONS.md) — no URL here is guessed from a naming pattern.

Uses `ingestion/pdf_extraction.py` (pypdf, real per-article splitting
where achievable, honest whole-document fallback where a PDF's layout
defeats it — see that module's docstring).

Run with: make ingest-building-bylaws
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
from ingestion.download_cache import download_cached
from ingestion.pdf_extraction import extract_pdf_bylaw

logger = structlog.get_logger(__name__)

PUBLISHER_PREFIX = "Administration communale"


class BylawEntry:
    __slots__ = ("commune_code", "commune_name", "url")

    def __init__(self, commune_code: str, commune_name: str, url: str) -> None:
        self.commune_code = commune_code
        self.commune_name = commune_name
        self.url = url


# Every URL verified live (real PDF, real extractable text) before being
# added — see DECISIONS.md for the two real PDF-layout failure modes found
# along the way (Wiltz/VDL/Schengen/Junglinster fall back to one
# whole-document chunk; Esch/Differdange/Dudelange/Sanem split per-article).
BUILDING_BYLAWS: list[BylawEntry] = [
    BylawEntry(
        "0304",
        "Luxembourg",
        "https://www.vdl.lu/sites/default/files/media/document/A1%20Reglement%2007-2018_0.pdf",
    ),
    BylawEntry(
        "0807",
        "Wiltz",
        "https://www.wiltz.lu/media/8f02c653-4928-4317-b76c-f3357d5a3614/"
        "reglement-communal-sur-les-batisses-les-voies-et-les-sites-pour-les-localites-de-"
        "wiltz-weidingen-roullingen-v20240821.pdf",
    ),
    BylawEntry(
        "0204",
        "Esch-sur-Alzette",
        "https://administration.esch.lu/wp-content/uploads/sites/2/2022/03/RBVS-Esch-Alzette.pdf",
    ),
    BylawEntry(
        "0202",
        "Differdange",
        "https://differdange.lu/wp-content/uploads/2023/11/Reglement-Batisses_2023.pdf",
    ),
    BylawEntry(
        "0203",
        "Dudelange",
        "https://sadudelangedata.blob.core.windows.net/files/2025/09/"
        "20250521_Dudelange_RBVS_Version-Coordonnee_2025-06.pdf",
    ),
    BylawEntry(
        "1206",
        "Schengen",
        "https://www.schengen.lu/wp-content/uploads/2020/09/RBVS_SCHENGEN_vf_280520.pdf",
    ),
    BylawEntry(
        "1105",
        "Junglinster",
        "https://www.junglinster.lu/media/605e3ccc-6c1d-4126-bdd5-d8e03a100bb3/"
        "reglement-sur-les-batisses-les-voies-publiques-et-les-sites-rbvs.pdf",
    ),
    BylawEntry(
        "0213",
        "Sanem",
        "https://www.suessem.lu/wp-content/uploads/2022/05/"
        "R%C3%A8glement-sur-les-B%C3%A2tisses-les-Voies-publiques-et-les-sites.pdf",
    ),
]


def _ingest_one(session: Session, entry: BylawEntry) -> Document | None:
    pdf_path = download_cached(entry.url, f"bylaw_{entry.commune_code}.pdf")
    pdf_bytes = pdf_path.read_bytes()
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    title, articles = extract_pdf_bylaw(str(pdf_path))

    publisher = f"{PUBLISHER_PREFIX} de {entry.commune_name}"
    source_stmt = (
        insert(Source)
        .values(
            name=f"Règlement sur les bâtisses — {entry.commune_name}",
            description="Building bylaw (règlement sur les bâtisses, les voies "
            f"publiques et les sites) for {entry.commune_name}.",
            source_url=entry.url,
            access_method=AccessMethod.scrape,
            publisher=publisher,
            commune_code=entry.commune_code,
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
            Document.source_url == entry.url,
            Document.sha256 == sha256,
        )
    ).scalar_one_or_none()
    if existing is not None:
        logger.info(
            "ingest.building_bylaw.unchanged",
            commune=entry.commune_name,
            document_id=str(existing.id),
        )
        return existing

    document = Document(
        source_id=source_id,
        source_url=entry.url,
        title=title or f"Règlement sur les bâtisses — {entry.commune_name}",
        publisher=publisher,
        sha256=sha256,
        language=Language.fr,
        commune_code=entry.commune_code,
        # A commune bylaw isn't tracked for amendment status the way a
        # Legilux act is — no equivalent "coordinated version" registry
        # exists for communal regulations, so this is honestly `unknown`
        # rather than asserted current (see DECISIONS.md).
        legal_status=LegalStatus.unknown,
        document_type=DocumentType.building_bylaw,
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
                document_type=DocumentType.building_bylaw,
                language=Language.fr,
                legal_status=LegalStatus.unknown,
                commune_code=entry.commune_code,
            )
        )

    logger.info(
        "ingest.building_bylaw.new_document",
        commune=entry.commune_name,
        document_id=str(document.id),
        articles=len(articles),
        whole_document_fallback=len(articles) == 1 and articles[0].article_ref is None,
    )
    return document


def ingest(session: Session) -> list[Document]:
    documents = []
    for entry in BUILDING_BYLAWS:
        document = _ingest_one(session, entry)
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
    logger.info("ingest.building_bylaws.complete", documents=count)


if __name__ == "__main__":
    main()
