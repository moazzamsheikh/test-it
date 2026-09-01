"""Address autocomplete search (M1.2): pg_trgm fuzzy match + a small
abbreviation table, applied at query time (see DECISIONS.md).

Does NOT solve full FR/DE/LB street-name-variant search — that needs CACLR's
ALIAS.RUE data (real alternate names per street), not a prefix-expansion
table, and is not ingested yet (see SOURCES.md). This only expands common
French street-type abbreviations (r. -> rue, etc.), which is a real but
narrower thing than the full multilingual-variant requirement.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cadastre import Address, Commune, Parcel
from app.schemas.address import AddressSearchResult

# Common French street-type abbreviations seen in Luxembourg addresses.
# Deliberately small and reviewable — not a substitute for real alias data.
STREET_ABBREVIATIONS: dict[str, str] = {
    "r.": "rue",
    "rte": "route",
    "av.": "avenue",
    "av": "avenue",
    "bd": "boulevard",
    "bd.": "boulevard",
    "pl.": "place",
    "ch.": "chemin",
}

_HOUSE_NUMBER_PREFIX = re.compile(r"^\s*(\d+[A-Za-z]?)\s+(.+)$")


def expand_abbreviations(query: str) -> str:
    tokens = query.split()
    return " ".join(STREET_ABBREVIATIONS.get(t.lower(), t) for t in tokens)


def split_house_number(query: str) -> tuple[str | None, str]:
    """ "1 Rue du Fort Thüngen" -> ("1", "Rue du Fort Thüngen"); no leading
    number -> (None, query unchanged)."""
    m = _HOUSE_NUMBER_PREFIX.match(query)
    if m:
        return m.group(1), m.group(2)
    return None, query


async def search_addresses(
    session: AsyncSession, raw_query: str, limit: int = 10
) -> list[AddressSearchResult]:
    house_number, street_part = split_house_number(raw_query.strip())
    expanded = expand_abbreviations(street_part)
    # Same normalization the stored column uses (unaccent + lower), computed
    # in SQL rather than reimplemented in Python, so it can never drift from
    # what street_name_normalized actually contains.
    normalized_query = func.unaccent_immutable(func.lower(expanded))
    score = func.similarity(Address.street_name_normalized, normalized_query)

    stmt = (
        select(
            Address.id,
            Address.street_name,
            Address.house_number,
            Address.locality,
            Address.postal_code,
            Address.admin_commune_code,
            Commune.name.label("admin_commune_name"),
            Parcel.cadastral_id.label("parcel_cadastral_id"),
            func.ST_X(func.ST_Transform(Address.geom, 4326)).label("lon"),
            func.ST_Y(func.ST_Transform(Address.geom, 4326)).label("lat"),
            score.label("score"),
        )
        .outerjoin(Commune, Commune.lau2_code == Address.admin_commune_code)
        .outerjoin(Parcel, Parcel.id == Address.parcel_id)
        .where(Address.street_name_normalized.op("%")(normalized_query))
        .order_by(score.desc())
        .limit(limit)
    )
    if house_number:
        stmt = stmt.where(Address.house_number.ilike(house_number))

    rows = (await session.execute(stmt)).all()
    return [AddressSearchResult.model_validate(row, from_attributes=True) for row in rows]
