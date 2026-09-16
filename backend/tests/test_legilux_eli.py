"""Unit tests for `ingestion/legilux_eli.py` — real filestore URL -> ELI
derivation, covering both real Legilux version-marker shapes (`consolide`
with a trailing date segment, `jo` without one)."""

from __future__ import annotations

from ingestion.legilux_eli import expression_eli_from_filestore_url, work_eli_from_filestore_url

_CONSOLIDE_URL = (
    "https://data.legilux.public.lu/filestore/eli/etat/leg/loi/2004/07/19/n1/consolide/20231001"
    "/fr/html/eli-etat-leg-loi-2004-07-19-n1-consolide-20231001-fr-html.html"
)
_JO_URL = (
    "https://data.legilux.public.lu/filestore/eli/etat/leg/loi/1979/02/25/n3/jo/fr/html/"
    "eli-etat-leg-loi-1979-02-25-n3-jo-fr-html.html"
)


def test_work_eli_from_consolide_url_drops_version_and_suffix() -> None:
    assert work_eli_from_filestore_url(_CONSOLIDE_URL) == (
        "http://data.legilux.public.lu/eli/etat/leg/loi/2004/07/19/n1"
    )


def test_expression_eli_from_consolide_url_keeps_the_date_segment() -> None:
    assert expression_eli_from_filestore_url(_CONSOLIDE_URL) == (
        "http://data.legilux.public.lu/eli/etat/leg/loi/2004/07/19/n1/consolide/20231001"
    )


def test_work_eli_from_jo_url_drops_jo_and_suffix() -> None:
    assert work_eli_from_filestore_url(_JO_URL) == (
        "http://data.legilux.public.lu/eli/etat/leg/loi/1979/02/25/n3"
    )


def test_expression_eli_from_jo_url_keeps_jo_with_no_trailing_date() -> None:
    assert expression_eli_from_filestore_url(_JO_URL) == (
        "http://data.legilux.public.lu/eli/etat/leg/loi/1979/02/25/n3/jo"
    )
