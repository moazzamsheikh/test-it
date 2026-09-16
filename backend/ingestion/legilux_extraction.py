"""Real-text extraction from Legilux's standard "richtext" HTML export
format (data.legilux.public.lu/filestore/.../jo/fr/html/....html) — verified
live against a real règlement grand-ducal (see DECISIONS.md). Reusable
across any Legilux law/RGD — the `richtext_body`/`richtext_article`
structure is Legilux's own consistent export format, not specific to one
document.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

_ARTICLE_RE = re.compile(r"^\s*(Art\.\s*\d+\w*)")


class LegiluxArticle:
    __slots__ = ("article_ref", "text")

    def __init__(self, article_ref: str | None, text: str) -> None:
        self.article_ref = article_ref
        self.text = text


def extract_legilux_document(html: str) -> tuple[str, list[LegiluxArticle]]:
    """Returns (title, articles) — one LegiluxArticle per real `Art. N`
    division, so each becomes its own retrievable chunk rather than one
    giant blob (matches the project's existing per-article PAG chunking)."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    # A consolidated law's <h1> nests the real short title as its first <p>,
    # followed by a table of amending acts (also real content, but that's
    # amendment-history metadata, not the document's name) — verified live
    # against a real 84-article consolidated law. Taking the whole h1's text
    # would run the two together with no separator. A single-act RGD's <h1>
    # has just the one <p>, so this is backward-compatible with every
    # document already ingested (see DECISIONS.md).
    title_el = h1.find("p") if h1 else None
    title = title_el.get_text(strip=True) if title_el else ""

    body = soup.find("div", class_="richtext_body")
    if body is None:
        raise ValueError(
            "expected a div.richtext_body container — unexpected Legilux page structure"
        )

    articles = []
    for article_div in body.find_all("div", class_="richtext_article"):
        # Legilux's export prefixes each article with a zero-width space
        # (verified live — not a parsing artifact to work around blindly,
        # a real character in the real markup).
        text = article_div.get_text(" ", strip=True).lstrip("​").strip()
        if not text:
            continue
        match = _ARTICLE_RE.match(text)
        article_ref = match.group(1) if match else None
        articles.append(LegiluxArticle(article_ref=article_ref, text=text))

    if not articles:
        raise ValueError("no div.richtext_article elements found — unexpected page structure")

    return title, articles


def eli_url_to_richtext_html_url(eli_url: str) -> str:
    """Transforms a `legilux.public.lu/eli/.../jo` link (the form Legilux's own
    GIS data uses, e.g. ZPIN's real `lien_legilux` attribute — see
    app/services/legilux_dynamic.py) into its real `data.legilux.public.lu`
    richtext HTML export URL. Confirmed mechanical, not a guess: verified
    against 8 real documents this project has ingested so far (4 sectoral
    plans, Findel, 2 flood RGDs, ZPIN's Gréngewald reserve) — every one
    follows `.../filestore/eli/<path>/fr/html/eli-<path-with-dashes>-fr-html.html`
    with no exceptions, where <path> is everything after "eli/" in the
    original link (e.g. "etat/leg/rgd/2024/01/24/a15/jo")."""
    path = eli_url.split("/eli/", 1)[1].strip("/")
    dashed = path.replace("/", "-")
    return f"https://data.legilux.public.lu/filestore/eli/{path}/fr/html/eli-{dashed}-fr-html.html"
