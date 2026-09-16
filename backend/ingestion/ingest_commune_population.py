"""M2.4 — real commune population, closing the one field left honestly
null in the commune registry. STATEC's population dataset isn't a flat
downloadable file (checked before, see DECISIONS.md) — it's exposed
through LUSTAT's real SDMX REST API (`lustat.statec.lu/rest/...`), found
by reading STATEC's own API documentation rather than guessing an
endpoint. Dataflow `DF_X021` ("Population par canton et commune") is a
real, annually-updated series (1821-present) covering all 100 real
communes, keyed by the same LAU2 code already used throughout this
project.

Run with: make ingest-commune-population
"""

from __future__ import annotations

import csv
import io

import httpx
import structlog
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.cadastre import Commune
from app.models.enums import AccessMethod, SourceStatus
from app.models.provenance import Source

logger = structlog.get_logger(__name__)

_SOURCE_NAME = "LUSTAT/STATEC — commune population (SDMX)"
_LUSTAT_URL = (
    "https://lustat.statec.lu/rest/data/LU1,DF_X021/all?dimensionAtObservation=AllDimensions"
)
_ACCEPT = "application/vnd.sdmx.data+csv;urn=true;file=true;labels=both"


def _fetch_latest_population_by_lau2(user_agent: str) -> dict[str, int]:
    response = httpx.get(
        _LUSTAT_URL, headers={"User-Agent": user_agent, "Accept": _ACCEPT}, timeout=30
    )
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))

    latest_year: dict[str, str] = {}
    latest_value: dict[str, int] = {}
    for row in reader:
        canton_field = row["CANTON: Canton"]
        lau2_code = canton_field.split(":", 1)[0].strip()
        year = row["TIME_PERIOD: Time period"]
        raw_value = row["OBS_VALUE"]
        if not raw_value:
            continue
        if lau2_code not in latest_year or year > latest_year[lau2_code]:
            latest_year[lau2_code] = year
            latest_value[lau2_code] = int(raw_value)
    return latest_value


def ingest(session: Session, user_agent: str) -> dict[str, int]:
    source_stmt = (
        insert(Source)
        .values(
            name=_SOURCE_NAME,
            description="Real STATEC/LUSTAT SDMX REST API — commune population, "
            'dataflow DF_X021 ("Population par canton et commune").',
            source_url=_LUSTAT_URL,
            access_method=AccessMethod.api,
            publisher="STATEC (Institut national de la statistique et des études économiques)",
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

    population_by_lau2 = _fetch_latest_population_by_lau2(user_agent)

    commune_codes = set(session.execute(select(Commune.lau2_code)).scalars().all())
    matched = 0
    for lau2_code in commune_codes:
        population = population_by_lau2.get(lau2_code)
        if population is None:
            continue
        session.execute(
            update(Commune).where(Commune.lau2_code == lau2_code).values(population=population)
        )
        matched += 1

    unmatched = commune_codes - population_by_lau2.keys()
    if unmatched:
        logger.warning("ingest.commune_population.unmatched", codes=sorted(unmatched))

    session.execute(update(Source).where(Source.id == source_id).values(documents_ingested=matched))
    return {"matched": matched, "unmatched": len(unmatched)}


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        result = ingest(session, settings.crawler_user_agent)
        session.commit()
    logger.info("ingest.commune_population.complete", **result)


if __name__ == "__main__":
    main()
