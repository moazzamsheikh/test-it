"""Real text extraction from PDF building bylaws (règlements sur les
bâtisses) — M2.3's PDF requirement. Every real bylaw PDF checked so far
(8 communes) has real, embedded (non-scanned) text — `pypdf` extracts it
directly; no OCR fallback was needed for any of them, so none is built
(a real, disclosed scope limit: a genuinely scanned bylaw PDF would need
Tesseract, not attempted here — see DECISIONS.md).
"""

from __future__ import annotations

import re

from pypdf import PdfReader

_ARTICLE_SPLIT_RE = re.compile(r"(?=\nArt\.?\s*\d+\w*[.\s])")
_ARTICLE_REF_RE = re.compile(r"^Art\.?\s*(\d+\w*)")
_MIN_ARTICLE_CHARS = 80
# A table-of-contents entry ("Art. 2 Objet ..................... 5") is a
# real, common false split — it starts with a real "Art. N" heading too,
# but is dominated by dot-leader characters rather than substantive text.
# Caught live: without this, Wiltz's real 60-ish articles became 301
# fragments, almost all TOC noise.
_DOT_LEADER_RE = re.compile(r"\.{5,}")


class PdfArticle:
    __slots__ = ("article_ref", "text")

    def __init__(self, article_ref: str | None, text: str) -> None:
        self.article_ref = article_ref
        self.text = text


def extract_pdf_bylaw(pdf_path: str) -> tuple[str, list[PdfArticle]]:
    """Returns (title, articles). Title is the first non-blank line of the
    first page (every real bylaw checked puts its own name there). Splits
    on real "Art. N" headings; a table-of-contents page listing article
    numbers produces short spurious fragments, filtered out by a minimum
    length rather than trying to detect "is this really a TOC" — real
    articles are substantive, TOC entries are one line."""
    reader = PdfReader(pdf_path)
    full_text = "\n".join(page.extract_text() for page in reader.pages)

    title = ""
    for line in full_text.splitlines():
        stripped = line.strip()
        if len(stripped) > 3:
            title = stripped
            break

    articles = []
    for fragment in _ARTICLE_SPLIT_RE.split(full_text):
        text = " ".join(fragment.split())
        if _DOT_LEADER_RE.search(text):
            continue
        if len(text) < _MIN_ARTICLE_CHARS:
            continue
        match = _ARTICLE_REF_RE.match(text)
        article_ref = f"Art. {match.group(1)}" if match else None
        articles.append(PdfArticle(article_ref=article_ref, text=text))

    # Two real, live-confirmed failure modes for per-article splitting,
    # not hypotheticals — both fall back to one whole-document chunk with
    # the real full text, rather than either fabricating a split or losing
    # the document (same precedent as
    # ingestion/pag_document_extraction.py's own whole-document chunks):
    # (1) no articles found at all — some communes' PDF export tool
    # separates "Art. N" labels from their body text in a way pypdf's
    # linear extraction never reunites (verified: "Art" appears zero times
    # anywhere in the extracted text for these, even though the document
    # visibly has articles); (2) articles found, but heavily duplicated —
    # a real body paragraph cross-referencing another article ("conformé-
    # ment à l'article 37") can start a new line right where the split
    # regex looks, over-splitting mid-paragraph (verified: one real
    # article number appeared 13 times in one document). A >30% duplicate
    # rate among real refs is treated as "the split isn't trustworthy"
    # rather than kept and reported as real structure it isn't.
    refs = [a.article_ref for a in articles if a.article_ref is not None]
    duplicate_rate = 1 - (len(set(refs)) / len(refs)) if refs else 0.0
    if not articles or duplicate_rate > 0.3:
        text = " ".join(full_text.split())
        if len(text) < _MIN_ARTICLE_CHARS:
            raise ValueError(f"no real text extracted at all from {pdf_path}")
        articles = [PdfArticle(article_ref=None, text=text)]

    return title, articles
