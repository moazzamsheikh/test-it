"""Real Legilux filestore URLs (what we actually fetch, e.g.
`.../loi/2004/07/19/n1/consolide/20231001/fr/html/...html`) encode the same
ELI (European Legislation Identifier) used by the SPARQL endpoint
(`data.legilux.public.lu/sparqlendpoint`), just with a different prefix and a
`/fr/html/<filename>` suffix tacked on. Deriving both ELI forms from the one
URL we already have avoids hand-typing 9 more identifiers that could drift
out of sync with the real fetch URL.

- "expression" ELI: identifies the exact version fetched, e.g.
  `.../eli/etat/leg/loi/2004/07/19/n1/consolide/20231001` — used as
  `Document.eli`.
- "work" ELI: the stable, version-independent identifier for the law itself,
  e.g. `.../eli/etat/leg/loi/2004/07/19/n1` — used as the SPARQL join key in
  `ingest_legislation_versions.py`.
"""

from __future__ import annotations

_ELI_HOST = "http://data.legilux.public.lu"


def _eli_path(filestore_url: str) -> list[str]:
    path = filestore_url.split("/filestore/", 1)[1]
    segments = path.split("/")
    # Drop the trailing `/fr/html/<filename>` (or similar) — real ELIs stop
    # right after the version marker segment. `consolide` is followed by a
    # date segment that's part of the ELI (`consolide/20231001`); `jo` (the
    # as-published original) has no such trailing date segment.
    if "consolide" in segments:
        idx = segments.index("consolide")
        return segments[: idx + 2]
    if "jo" in segments:
        idx = segments.index("jo")
        return segments[: idx + 1]
    raise ValueError(f"no recognised version marker in {filestore_url!r}")


def expression_eli_from_filestore_url(filestore_url: str) -> str:
    return f"{_ELI_HOST}/{'/'.join(_eli_path(filestore_url))}"


def work_eli_from_filestore_url(filestore_url: str) -> str:
    segments = _eli_path(filestore_url)
    marker = "consolide" if "consolide" in segments else "jo"
    return f"{_ELI_HOST}/{'/'.join(segments[: segments.index(marker)])}"
