"""M2.4 — the commune registry: real official website URL for all 102
communes, sourced from SYVICOL's own commune directory
(syvicol.lu/fr/annuaires/annuaire-des-communes) rather than guessed from a
domain-name pattern (many communes don't follow "www.<name>.lu" — verified
by actually reading each real page). LAU code/name/canton/district already
exist in `communes` from the M1 foundation (`Limites administratives`) —
this only adds the fields M2.4 asks for on top of that: `website_url`,
`geoportal_slug`, `population` (left null — no free-file population source
found within the time available, see DECISIONS.md), `cms_hosting_provider`
(left null here — filled only for the real sample investigated for
SCALING.md, not fabricated for the rest).

Run with: make ingest-commune-registry
"""

from __future__ import annotations

import html as html_module
import re
import unicodedata

import structlog
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.cadastre import Commune
from ingestion.download_cache import download_cached

logger = structlog.get_logger(__name__)

_DIRECTORY_URL = "https://www.syvicol.lu/fr/annuaires/annuaire-des-communes"
_DETAIL_URL = "https://www.syvicol.lu/fr/annuaires/annuaire-des-communes/fichecommune/{slug}"

_SLUG_RE = re.compile(r"fichecommune/([a-z0-9-]+)")
_SITE_LABEL_RE = re.compile(r"Site\s*:\s*</span>\s*<a\s+href=\"([^\"]+)\"")
_H1_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>")


def _normalize(name: str) -> str:
    # SYVICOL's real <h1> markup has real, unescaped HTML entities (e.g.
    # "VALLEE DE L&#39;ERNZ") — verified live, not a hypothetical case: this
    # was the one real mismatch out of 100 real communes on the first run.
    unescaped = html_module.unescape(name)
    decomposed = unicodedata.normalize("NFKD", unescaped)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return ascii_only.strip().lower().replace("-", " ")


def _fetch_directory_slugs() -> list[str]:
    path = download_cached(_DIRECTORY_URL, "syvicol_annuaire_communes.html")
    html = path.read_text(encoding="utf-8")
    return sorted(set(_SLUG_RE.findall(html)))


def _fetch_commune_detail(slug: str) -> tuple[str, str | None]:
    url = _DETAIL_URL.format(slug=slug)
    path = download_cached(url, f"syvicol_commune_{slug}.html")
    html = path.read_text(encoding="utf-8")
    h1_match = _H1_RE.search(html)
    name = h1_match.group(1).strip() if h1_match else slug
    site_match = _SITE_LABEL_RE.search(html)
    website_url = site_match.group(1) if site_match else None
    return name, website_url


def ingest(session: Session) -> dict[str, int]:
    slugs = _fetch_directory_slugs()
    logger.info("ingest.commune_registry.slugs_found", count=len(slugs))

    communes_by_normalized_name = {
        _normalize(c.name): c for c in session.execute(select(Commune)).scalars().all()
    }

    matched = 0
    unmatched: list[str] = []
    for slug in slugs:
        name, website_url = _fetch_commune_detail(slug)
        commune = communes_by_normalized_name.get(_normalize(name))
        if commune is None:
            unmatched.append(name)
            continue
        session.execute(
            update(Commune)
            .where(Commune.lau2_code == commune.lau2_code)
            .values(website_url=website_url, geoportal_slug=commune.name)
        )
        matched += 1

    if unmatched:
        logger.warning("ingest.commune_registry.unmatched", names=unmatched)
    logger.info("ingest.commune_registry.complete", matched=matched, unmatched=len(unmatched))
    return {"matched": matched, "unmatched": len(unmatched)}


def main() -> None:
    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        result = ingest(session)
        session.commit()
    logger.info("ingest.commune_registry.done", **result)


if __name__ == "__main__":
    main()
