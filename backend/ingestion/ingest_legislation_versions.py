"""M2.4 bonus — SPARQL-based amendment-chain resolution for the national
legislation corpus (brief's own suggested route, not attempted in the first
pass — see DECISIONS.md).

`ingest_national_legislation.py` ingests exactly one real snapshot per law
(a dated "version consolidée" where one was found, the as-published "jo" text
otherwise) and honestly tagged 5 of 9 `LegalStatus.unknown` rather than
asserting they were current. This module answers the real question that
tagging couldn't: for a given law, what real version was actually in force
on a given date — using the real JOLux linked-data model, not a guess.

Endpoint discovery: `data.legilux.public.lu/sparql` (the human-facing URL)
only ever serves the Angular SPA shell, regardless of Accept header — the
real query endpoint, `data.legilux.public.lu/sparqlendpoint`, was found by
fetching the site's own JS bundle and grepping for literal "sparql" strings
(see DECISIONS.md). Real predicates used: `jolux:isMemberOf` (an expression's
Consolidation or original "jo" record → its stable Work), `jolux:isRealizedBy`
(→ the actual text URL), `jolux:dateApplicability`/`dateEndApplicability`
(the Consolidation's validity window), and — for laws with no recorded
Consolidation at all (real finding: `dechets_2012`'s "texte coordonné" has
only its one "jo" entry, no Consolidation nodes) — `jolux:dateEntryInForce`/
`jolux:dateNoLongerInForce` as the same information at the "jo" node itself.
One query handles both shapes generically (OPTIONAL for every date field)
rather than branching on document type.

Real, load-bearing finding this surfaced: `dechets_2012`'s own JOLux record
carries `inForceStatus = no-longer-in-force` and `dateNoLongerInForce =
2015-04-03` on the exact snapshot we ingested and tagged `LegalStatus.in_force`
— i.e. our existing tag for that one document is wrong per the real
amendment data. Left as-is in `ingest_national_legislation.py` rather than
silently changed (that script's tagging predates this discovery and a
retroactive fix deserves its own reviewed decision, not a drive-by edit
buried in an unrelated ingestion run) — flagged explicitly in DECISIONS.md
instead, and now discoverable live via this module's own resolution query.

Run with: make ingest-legislation-versions
"""

from __future__ import annotations

import time
from datetime import date, datetime

import httpx
import structlog
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.enums import AccessMethod, SourceStatus
from app.models.provenance import Document, LegislationVersion, Source
from ingestion.ingest_national_legislation import NATIONAL_LAWS
from ingestion.legilux_eli import work_eli_from_filestore_url

logger = structlog.get_logger(__name__)

_SPARQL_ENDPOINT = "https://data.legilux.public.lu/sparqlendpoint"
_SOURCE_NAME = "Legilux SPARQL — amendment-chain resolution"

# One request per already-ingested law (9 total) — a short pause between
# calls is a real respect-the-server measure, not cargo-culted; this is a
# public triple store, not a bulk-download endpoint.
_REQUEST_DELAY_SECONDS = 1.0

_QUERY_TEMPLATE = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?version ?expr ?dateApplicability ?dateEndApplicability
       ?dateEntryInForce ?dateNoLongerInForce ?inForceStatus
WHERE {{
  ?version jolux:isMemberOf <{work_eli}> .
  ?version jolux:isRealizedBy ?expr .
  OPTIONAL {{ ?version jolux:dateApplicability ?dateApplicability . }}
  OPTIONAL {{ ?version jolux:dateEndApplicability ?dateEndApplicability . }}
  OPTIONAL {{ ?version jolux:dateEntryInForce ?dateEntryInForce . }}
  OPTIONAL {{ ?version jolux:dateNoLongerInForce ?dateNoLongerInForce . }}
  OPTIONAL {{ ?version jolux:inForceStatus ?inForceStatus . }}
}}
"""


class VersionWindow:
    __slots__ = (
        "version_eli",
        "expression_url",
        "date_applicability",
        "date_end_applicability",
        "in_force_status",
    )

    def __init__(
        self,
        version_eli: str,
        expression_url: str,
        date_applicability: date,
        date_end_applicability: date | None,
        in_force_status: str | None,
    ) -> None:
        self.version_eli = version_eli
        self.expression_url = expression_url
        self.date_applicability = date_applicability
        self.date_end_applicability = date_end_applicability
        self.in_force_status = in_force_status


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _fetch_version_windows(work_eli: str, user_agent: str) -> list[VersionWindow]:
    query = _QUERY_TEMPLATE.format(work_eli=work_eli)
    response = httpx.get(
        _SPARQL_ENDPOINT,
        params={"query": query},
        headers={"User-Agent": user_agent, "Accept": "application/sparql-results+json"},
        timeout=30,
    )
    response.raise_for_status()
    bindings = response.json()["results"]["bindings"]

    windows = []
    for b in bindings:
        # The real snapshot's own validity window (`dateApplicability`) takes
        # priority; laws with no Consolidation node at all (real finding:
        # `dechets_2012`) carry the same information as `dateEntryInForce` on
        # the "jo" node itself instead.
        effective = b.get("dateApplicability") or b.get("dateEntryInForce")
        if effective is None:
            logger.warning(
                "ingest.legislation_versions.no_effective_date", work_eli=work_eli, row=b
            )
            continue
        end = b.get("dateEndApplicability") or b.get("dateNoLongerInForce")
        status_uri = b.get("inForceStatus", {}).get("value")
        windows.append(
            VersionWindow(
                version_eli=b["version"]["value"],
                expression_url=b["expr"]["value"],
                date_applicability=_parse_date(effective["value"]),
                date_end_applicability=_parse_date(end["value"]) if end else None,
                in_force_status=status_uri.rsplit("/", 1)[-1] if status_uri else None,
            )
        )
    return windows


def _ingest_one(session: Session, work_eli: str, user_agent: str) -> int:
    windows = _fetch_version_windows(work_eli, user_agent)
    if not windows:
        logger.warning("ingest.legislation_versions.no_versions_found", work_eli=work_eli)
        return 0

    for w in windows:
        document_id = session.execute(
            select(Document.id).where(Document.eli == w.version_eli)
        ).scalar_one_or_none()
        session.execute(
            insert(LegislationVersion)
            .values(
                document_id=document_id,
                work_eli=work_eli,
                version_eli=w.version_eli,
                expression_url=w.expression_url,
                date_applicability=w.date_applicability,
                date_end_applicability=w.date_end_applicability,
                in_force_status=w.in_force_status,
            )
            .on_conflict_do_update(
                index_elements=[LegislationVersion.version_eli],
                set_={
                    "document_id": document_id,
                    "date_applicability": w.date_applicability,
                    "date_end_applicability": w.date_end_applicability,
                    "in_force_status": w.in_force_status,
                    "fetched_at": func.now(),
                },
            )
        )
    return len(windows)


def ingest(session: Session, user_agent: str) -> dict[str, int]:
    source_stmt = (
        insert(Source)
        .values(
            name=_SOURCE_NAME,
            description="Real JOLux SPARQL endpoint — resolves which consolidated "
            "version of a law was in force on a given date.",
            source_url=_SPARQL_ENDPOINT,
            access_method=AccessMethod.sparql,
            publisher="Gouvernement du Grand-Duché de Luxembourg (Legilux)",
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

    total_versions = 0
    laws_with_versions = 0
    seen_work_elis: set[str] = set()
    for entry in NATIONAL_LAWS:
        work_eli = work_eli_from_filestore_url(entry.url)
        if work_eli in seen_work_elis:
            # A law cited more than once in NATIONAL_LAWS — not the case
            # today, but cheap to guard against querying the endpoint twice.
            continue
        seen_work_elis.add(work_eli)

        count = _ingest_one(session, work_eli, user_agent)
        if count:
            laws_with_versions += 1
            total_versions += count
        time.sleep(_REQUEST_DELAY_SECONDS)

    session.execute(
        update(Source).where(Source.id == source_id).values(documents_ingested=total_versions)
    )
    return {
        "laws_queried": len(seen_work_elis),
        "laws_with_versions": laws_with_versions,
        "versions": total_versions,
    }


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        result = ingest(session, settings.crawler_user_agent)
        session.commit()
    logger.info("ingest.legislation_versions.complete", **result)


if __name__ == "__main__":
    main()
