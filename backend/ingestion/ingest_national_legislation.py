"""M2.3/M2.4 — the national legislation corpus named explicitly in the
assessment brief (§3.3's "Texts to ingest — coordinated versions, in force").

Two real Legilux document *shapes* are used, both handled by the same
existing extractor (`legilux_extraction.extract_legilux_document` — the
`richtext_body`/`richtext_article` structure is shared across all of them):

- `consolide/<date>` — a real, dated "version consolidée" snapshot. Used
  wherever one was found and verified (see DECISIONS.md) — tagged
  `LegalStatus.in_force` since it's a genuine coordinated-in-force text, not
  just the original enactment.
- `jo` — the original as-published text. Used where a consolidated snapshot
  could not be found within the time available — tagged
  `LegalStatus.unknown` rather than asserted as current, since none of
  these laws' amendment history has been verified against this text. This
  is an honest, deliberate scope limit (see PROGRESS.md), not an oversight:
  a rigorous amendment-chain-aware ingestion (the SPARQL-endpoint route the
  brief itself points at) is real, further work, not done today.

One entry, `patrimoine_culturel`, cites a different real law (25 February
2022) than the brief's stated date (8 September 2023) — searched
extensively and could not find a real law at that exact date on this
subject; the 25 February 2022 law is the real, verified, correctly-titled
"loi ... relative au patrimoine culturel" in force. Flagged here rather
than silently substituted.

Run with: make ingest-national-legislation
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
from ingestion.legilux_eli import expression_eli_from_filestore_url
from ingestion.legilux_extraction import extract_legilux_document

logger = structlog.get_logger(__name__)

PUBLISHER = "Gouvernement du Grand-Duché de Luxembourg (Legilux)"

_BASE = "https://data.legilux.public.lu/filestore/eli/etat/leg"


class NationalLawEntry:
    __slots__ = ("key", "label", "url", "legal_status")

    def __init__(self, key: str, label: str, url: str, legal_status: LegalStatus) -> None:
        self.key = key
        self.label = label
        self.url = url
        self.legal_status = legal_status


NATIONAL_LAWS: list[NationalLawEntry] = [
    NationalLawEntry(
        "acdu_2004",
        "Loi du 19 juillet 2004 concernant l'aménagement communal et le développement urbain",
        f"{_BASE}/loi/2004/07/19/n1/consolide/20231001/fr/html/"
        "eli-etat-leg-loi-2004-07-19-n1-consolide-20231001-fr-html.html",
        LegalStatus.in_force,
    ),
    NationalLawEntry(
        "amenagement_territoire_2018",
        "Loi du 17 avril 2018 concernant l'aménagement du territoire",
        f"{_BASE}/loi/2018/04/17/a271/jo/fr/html/eli-etat-leg-loi-2018-04-17-a271-jo-fr-html.html",
        LegalStatus.unknown,
    ),
    NationalLawEntry(
        "etablissements_classes_1999",
        "Loi du 10 juin 1999 relative aux établissements classés",
        f"{_BASE}/loi/1999/06/10/n5/jo/fr/html/eli-etat-leg-loi-1999-06-10-n5-jo-fr-html.html",
        LegalStatus.unknown,
    ),
    NationalLawEntry(
        "protection_nature_2018",
        "Loi du 18 juillet 2018 concernant la protection de la nature et des ressources naturelles",
        f"{_BASE}/loi/2018/07/18/a771/consolide/20231001/fr/html/"
        "eli-etat-leg-loi-2018-07-18-a771-consolide-20231001-fr-html.html",
        LegalStatus.in_force,
    ),
    NationalLawEntry(
        "eau_2008",
        "Loi du 19 décembre 2008 relative à l'eau",
        f"{_BASE}/loi/2008/12/19/n17/consolide/20250101/fr/html/"
        "eli-etat-leg-loi-2008-12-19-n17-consolide-20250101-fr-html.html",
        LegalStatus.in_force,
    ),
    NationalLawEntry(
        "dechets_2012",
        "Loi du 21 mars 2012 relative à la gestion des déchets (texte coordonné)",
        f"{_BASE}/tc/2014/12/10/n2/jo/fr/html/eli-etat-leg-tc-2014-12-10-n2-jo-fr-html.html",
        LegalStatus.in_force,
    ),
    NationalLawEntry(
        "aide_logement_1979",
        "Loi du 25 février 1979 concernant l'aide au logement",
        f"{_BASE}/loi/1979/02/25/n3/jo/fr/html/eli-etat-leg-loi-1979-02-25-n3-jo-fr-html.html",
        LegalStatus.unknown,
    ),
    NationalLawEntry(
        "accessibilite_2022",
        "Loi du 7 janvier 2022 relative à l'accessibilité des lieux ouverts au public",
        f"{_BASE}/loi/2022/01/07/a26/jo/fr/html/eli-etat-leg-loi-2022-01-07-a26-jo-fr-html.html",
        LegalStatus.unknown,
    ),
    NationalLawEntry(
        "patrimoine_culturel_2022",
        # Brief cites "8 September 2023" — no real law at that exact date on
        # this subject was found after real searching; this is the real,
        # verified, correctly-titled current law instead (see module docstring).
        "Loi du 25 février 2022 relative au patrimoine culturel",
        f"{_BASE}/loi/2022/02/25/a80/jo/fr/html/eli-etat-leg-loi-2022-02-25-a80-jo-fr-html.html",
        LegalStatus.unknown,
    ),
]


def _ingest_one(session: Session, entry: NationalLawEntry) -> Document | None:
    html_path = download_cached(entry.url, f"legilux_law_{entry.key}.html")
    html = html_path.read_text(encoding="utf-8")
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    title, articles = extract_legilux_document(html)

    source_stmt = (
        insert(Source)
        .values(
            name=f"Legilux — {entry.label}",
            description="National legislation named in the assessment brief §3.3.",
            source_url=entry.url,
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

    eli = expression_eli_from_filestore_url(entry.url)

    existing = session.execute(
        select(Document).where(Document.source_url == entry.url, Document.sha256 == sha256)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.eli != eli:
            existing.eli = eli
        logger.info("ingest.national_law.unchanged", key=entry.key, document_id=str(existing.id))
        return existing

    document = Document(
        source_id=source_id,
        eli=eli,
        source_url=entry.url,
        title=title or entry.label,
        publisher=PUBLISHER,
        sha256=sha256,
        language=Language.fr,
        legal_status=entry.legal_status,
        document_type=DocumentType.loi,
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
                document_type=DocumentType.loi,
                language=Language.fr,
                legal_status=entry.legal_status,
            )
        )

    logger.info(
        "ingest.national_law.new_document",
        key=entry.key,
        document_id=str(document.id),
        articles=len(articles),
        legal_status=entry.legal_status.value,
    )
    return document


def ingest(session: Session) -> list[Document]:
    documents = []
    for entry in NATIONAL_LAWS:
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
    logger.info("ingest.national_legislation.complete", documents=count)


if __name__ == "__main__":
    main()
