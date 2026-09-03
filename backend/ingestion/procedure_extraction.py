"""Real-content extraction for one specific guichet.public.lu procedure page
(M5, scoped deliberately small — see DECISIONS.md: a full crawler is M2's
job; this parses exactly the one page structure it was written against, not
a generic scraper).

Kept separate from the ingestion script so it's a pure function testable
against a saved real-page fixture (tests/fixtures/guichet_autorisation_batir.html)
without a live network call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

# The real section headings on the real page, in the order we want them
# displayed — chosen by reading the actual page (see DECISIONS.md), not
# guessed. Anything else on the page (feedback forms, footer, related-links
# boilerplate) is deliberately not extracted.
_SECTION_HEADINGS = [
    "Personnes pouvant introduire une demande",
    "Travaux soumis à une autorisation de construire",
    "Introduction de la demande / de la déclaration",
    "Obligations",
    "Autres autorisations requises",
    "Durée de validité",
]


@dataclass
class ProcedureSection:
    heading: str
    text: str


@dataclass
class LegalReference:
    label: str
    url: str


@dataclass
class ExtractedProcedure:
    title: str
    document_date_str: str | None  # raw "DD.MM.YYYY" as found on the page, or None
    sections: list[ProcedureSection]
    legal_references: list[LegalReference]


def extract_procedure(html: str) -> ExtractedProcedure:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if main is None:
        raise ValueError("expected a <main> element — page structure has changed")

    title_tag = main.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    sections = []
    for heading_tag in main.find_all(["h2", "h3"]):
        heading_text = heading_tag.get_text(strip=True)
        if heading_text not in _SECTION_HEADINGS:
            continue
        parts: list[str] = []
        node = heading_tag.find_next_sibling()
        while node is not None and node.name not in ("h2", "h3"):
            text = node.get_text(" ", strip=True)
            if text:
                parts.append(text)
            node = node.find_next_sibling()
        if parts:
            sections.append(ProcedureSection(heading=heading_text, text="\n".join(parts)))

    legal_references = [
        LegalReference(label=a.get_text(strip=True), url=str(a["href"]))
        for a in main.find_all("a", href=True)
        if "legilux" in str(a["href"]).lower()
    ]

    # The page shows exactly one DD.MM.YYYY-shaped date; treated as the
    # page's own last-updated stamp (not a clearly-labelled field, so this is
    # an honest best-effort, documented as such in DECISIONS.md).
    date_match = re.search(r"\b([0-3]?\d\.[01]?\d\.20\d{2})\b", html)

    return ExtractedProcedure(
        title=title,
        document_date_str=date_match.group(1) if date_match else None,
        sections=sections,
        legal_references=legal_references,
    )
