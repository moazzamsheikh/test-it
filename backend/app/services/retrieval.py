"""M3.1 — minimal retrieval core, built to make EVAL.md's numbers real
rather than fabricated (see DECISIONS.md: a full M3 — chatbot UI,
reranking, conversation memory — was explicitly out of scope for today;
this is only the retrieval function needed to measure precision/recall on
a golden set).

Lexical only, not hybrid: `chunks.embedding` (pgvector, HNSW-indexed) has
been part of the schema since the M1/M2 foundation, but nothing has ever
been written to it — no embedding API key is configured in this
environment (no `.env`, `anthropic_api_key` empty). `chunks.tsv` (a
generated, GIN-indexed Postgres full-text column, `to_tsvector('simple',
text)`) has been populated automatically for every chunk since it was
first ingested, with zero extra ingestion work — a real head start from
how M2's schema was designed. Legal text (article numbers, defined terms)
is exactly what full-text search handles well and dense embeddings lose,
per the brief's own M3.1 rationale — so this is a real, if partial,
retrieval mechanism, not a placeholder.

Metadata filtering (M3.1's other explicit requirement — "a query about a
parcel in Wiltz must not retrieve the Luxembourg City building bylaw")
uses `commune_code`, already denormalised onto every chunk.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DocumentType
from app.models.provenance import Chunk, Document

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# The 'simple' Postgres text-search config was deliberately chosen over
# 'french' to avoid stemming that would mangle legal terms/article numbers
# (see the Chunk model's own comment) — but 'simple' also skips stopword
# removal, unlike 'french'. Combined with OR-ing every query token, that
# let common function words ("de", "des", "pour") dominate `ts_rank_cd`
# over the actually-meaningful rare terms — caught live: a real query
# about "établissements classés" ranked unrelated PAG documents above the
# real establishments law, because those documents happened to repeat
# "des"/"les" more often. A minimal, hand-picked French stopword list
# fixes this without giving up the no-stemming guarantee.
_STOPWORDS = frozenset(
    {
        "de",
        "des",
        "du",
        "un",
        "une",
        "le",
        "la",
        "les",
        "et",
        "ou",
        "pour",
        "dans",
        "sur",
        "avec",
        "sans",
        "est",
        "sont",
        "qui",
        "que",
        "quel",
        "quelle",
        "quels",
        "quelles",
        "comment",
        "combien",
        "ce",
        "cet",
        "cette",
        "ces",
        "à",
        "au",
        "aux",
        "en",
        "par",
        "plus",
        "se",
        "sa",
        "son",
        "ses",
        "il",
        "elle",
        "il_y_a",
        "y",
        "a",
        "d",
        "l",
        "s",
        "on",
    }
)


def _or_tsquery(query: str) -> str:
    """`plainto_tsquery`/`websearch_to_tsquery` both AND every word together
    — correct for a search box, wrong for a natural-language question: a
    real question ("Combien de classes existent pour...") shares almost no
    exact vocabulary with the formal article it's asking about, so an
    AND-of-all-words match returned zero results for nearly every real
    golden-set question (caught by actually running the eval, not assumed
    — see DECISIONS.md). OR-ing the tokens instead lets `ts_rank_cd` do its
    job: score by how many/how rare the matching terms are, the same way a
    real search engine ranks partial matches above rejecting them outright.
    """
    all_tokens = _WORD_RE.findall(query.lower())
    tokens = [t for t in all_tokens if t not in _STOPWORDS and len(t) > 1] or all_tokens
    return " | ".join(tokens) if tokens else query


class RetrievedChunk:
    __slots__ = ("chunk_id", "document_id", "document_title", "article_ref", "text", "rank")

    def __init__(
        self,
        chunk_id: uuid.UUID,
        document_id: uuid.UUID,
        document_title: str | None,
        article_ref: str | None,
        text: str,
        rank: float,
    ) -> None:
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.document_title = document_title
        self.article_ref = article_ref
        self.text = text
        self.rank = rank


async def search_chunks(
    session: AsyncSession,
    query: str,
    *,
    commune_code: str | None = None,
    document_type: DocumentType | None = None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Real Postgres full-text ranking (`ts_rank_cd`), not a substring
    match — tokens are OR-ed together (see `_or_tsquery`), each run through
    the same 'simple' (unstemmed) config `tsv` itself was built with, so a
    query and its matching article use the same tokenisation."""
    tsquery = func.to_tsquery("simple", _or_tsquery(query))
    # Normalization option 2 ("rank / document length") — without it, a
    # huge chunk (PAG documents are ingested as one giant chunk per
    # document, unlike Legilux's per-article chunks — see
    # ingestion/pag_document_extraction.py) can rank above a short, truly
    # relevant article purely by containing more raw text overall, not by
    # being more relevant. Caught live: a real Findel-servitude query
    # ranked an unrelated, enormous PAG zone document first, with literally
    # zero of the query's words present in it.
    rank = func.ts_rank_cd(Chunk.tsv, tsquery, 2).label("rank")

    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.article_ref,
            Chunk.text,
            Document.title,
            rank,
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.tsv.op("@@")(tsquery))
    )
    if commune_code is not None:
        stmt = stmt.where(Chunk.commune_code == commune_code)
    if document_type is not None:
        stmt = stmt.where(Chunk.document_type == document_type)
    stmt = stmt.order_by(rank.desc()).limit(limit)

    rows = (await session.execute(stmt)).all()
    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            document_title=row.title,
            article_ref=row.article_ref,
            text=row.text,
            rank=float(row.rank),
        )
        for row in rows
    ]
