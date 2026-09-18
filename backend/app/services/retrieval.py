"""M3.1 — hybrid retrieval: lexical (Postgres full-text) + dense (pgvector),
fused with Reciprocal Rank Fusion, then reranked (see `app/services/reranking.py`)
before generation.

Why hybrid, not pure vector (brief's own M3.1 rationale, confirmed concretely
in this corpus): dense embeddings are asked to represent a whole legal
article in one 1024-d vector and are known to blur article numbers, defined
terms and rare tokens. Lexical full-text search is exactly the opposite
failure mode — it can't generalise across paraphrase, but it never loses an
exact "Art. 19" or a proper noun. `app/services/embeddings.py` documents a
second, corpus-specific case for the same conclusion: ~94 oversized
whole-document chunks are truncated before embedding (only the *start* of
the document is represented densely), so lexical search — which scans the
whole chunk — is the only signal that can find something buried later in
one of those.

Fusion method: Reciprocal Rank Fusion (RRF), `score = sum(1 / (k + rank))`
across whichever ranked list(s) a chunk appears in, k=60 (the standard
constant from the original RRF paper and how e.g. Elasticsearch/Weaviate
default it). Chosen over score-normalisation-and-sum because `ts_rank_cd`
and cosine similarity live on incomparable scales with no principled way to
merge them numerically — RRF sidesteps that by fusing ranks, not raw scores.

Metadata filtering (brief's explicit requirement: "parcel context filters
the retrieval space *before* scoring, not after") is applied as a SQL WHERE
clause in both the lexical and dense queries, never as a post-hoc filter on
already-ranked results — see `_scope_clause`.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import structlog
from google.genai import errors as genai_errors
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DocumentType, LegalStatus
from app.models.provenance import Chunk, Document
from app.services.embeddings import embed_query

logger = structlog.get_logger(__name__)

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# A repealed/superseded provision must never be presented as current
# (M3.2, debrief Q9) — excluded at the SQL level so it is never even a
# retrieval candidate, not filtered out after the fact where a bug could
# let one slip through. `unknown` (freshly fetched, status not yet
# determined — see DECISIONS.md) and `draft` remain candidates: `unknown`
# isn't *known* to be repealed, and a `draft` provision is a real, citable
# fact about a pending change (M3.2's "the rule is ambiguous/about to
# change" case), just never presented as settled current law — that
# distinction is made in the chatbot's prompt (app/services/chatbot.py),
# not by hiding drafts from retrieval entirely.
_EXCLUDED_STATUSES = (LegalStatus.repealed, LegalStatus.superseded)

# Standard RRF constant (see module docstring).
_RRF_K = 60

# The 'simple' Postgres text-search config was deliberately chosen over
# 'french' to avoid stemming that would mangle legal terms/article numbers
# (see the Chunk model's own comment) — but 'simple' also skips stopword
# removal, unlike 'french'. Combined with OR-ing every query token, that
# let common function words ("de", "des", "pour") dominate `ts_rank_cd`
# over the actually-meaningful rare terms — caught live: a real query
# about "établissements classés" ranked unrelated PAG documents above the
# real establishments law, because those documents happened to repeat
# "des"/"les" more often. A minimal, hand-picked stopword list (FR/DE/EN —
# extended for M3's multilingual requirement; LB not included, see
# app/services/embeddings.py for why) fixes this without giving up the
# no-stemming guarantee.
_STOPWORDS = frozenset(
    {
        # French
        "de", "des", "du", "un", "une", "le", "la", "les", "et", "ou", "pour",
        "dans", "sur", "avec", "sans", "est", "sont", "qui", "que", "quel",
        "quelle", "quels", "quelles", "comment", "combien", "ce", "cet",
        "cette", "ces", "à", "au", "aux", "en", "par", "plus", "se", "sa",
        "son", "ses", "il", "elle", "y", "a", "d", "l", "s", "on",
        # German
        "der", "die", "das", "den", "dem", "ein", "eine", "einer",
        "und", "oder", "für", "mit", "ohne", "ist", "sind", "welche",
        "welcher", "welches", "wie", "wieviel", "was", "wer", "wo", "im",
        "in", "auf", "zu", "zum", "zur", "von", "vom", "bei", "kann", "man",
        # English
        "the", "an", "and", "or", "for", "with", "without", "is", "are",
        "which", "what", "how", "many", "much", "this", "that", "these",
        "those", "to", "of", "at", "can", "i",
    }
)  # fmt: skip


def meaningful_tokens(text: str) -> set[str]:
    """Lowercase content words (stopwords and single letters dropped) —
    shared by `_or_tsquery` below and, deliberately, by
    `app/services/llm/extractive.py`'s relevance heuristic, so "what counts
    as a meaningful word" has one definition rather than two that could
    drift apart."""
    all_tokens = _WORD_RE.findall(text.lower())
    tokens = {t for t in all_tokens if t not in _STOPWORDS and len(t) > 1}
    return tokens or set(all_tokens)


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
    tokens = meaningful_tokens(query)
    return " | ".join(tokens) if tokens else query


class RetrievedChunk:
    __slots__ = (
        "chunk_id",
        "document_id",
        "document_title",
        "source_url",
        "document_type",
        "legal_status",
        "commune_code",
        "article_ref",
        "text",
        "rank",
    )

    def __init__(
        self,
        chunk_id: uuid.UUID,
        document_id: uuid.UUID,
        document_title: str | None,
        source_url: str,
        document_type: DocumentType,
        legal_status: LegalStatus,
        commune_code: str | None,
        article_ref: str | None,
        text: str,
        rank: float,
    ) -> None:
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.document_title = document_title
        self.source_url = source_url
        self.document_type = document_type
        self.legal_status = legal_status
        self.commune_code = commune_code
        self.article_ref = article_ref
        self.text = text
        self.rank = rank


def _scope_clause(
    stmt: Select[Any],
    *,
    commune_code: str | None,
    include_national: bool,
    document_type: DocumentType | None,
) -> Select[Any]:
    """Applied to both the lexical and dense candidate queries so parcel
    context narrows the search space *before* scoring, not after (brief's
    explicit M3.1 requirement) — never as a post-hoc `if` on already-ranked
    Python results, which real bugs (a repealed doc slipping through a
    result-shaping step written after the query, say) could bypass."""
    stmt = stmt.where(Chunk.legal_status.notin_(_EXCLUDED_STATUSES))
    if commune_code is not None:
        if include_national:
            # A query about a Wiltz parcel must not retrieve the Luxembourg
            # City building bylaw (brief's own example) — but it MUST still
            # retrieve national legislation, which applies to every commune
            # and is stored with commune_code=NULL (see provenance.py).
            stmt = stmt.where((Chunk.commune_code == commune_code) | (Chunk.commune_code.is_(None)))
        else:
            stmt = stmt.where(Chunk.commune_code == commune_code)
    if document_type is not None:
        stmt = stmt.where(Chunk.document_type == document_type)
    return stmt


def _row_to_chunk(row: object, rank: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.id,  # type: ignore[attr-defined]
        document_id=row.document_id,  # type: ignore[attr-defined]
        document_title=row.title,  # type: ignore[attr-defined]
        source_url=row.source_url,  # type: ignore[attr-defined]
        document_type=row.document_type,  # type: ignore[attr-defined]
        legal_status=row.legal_status,  # type: ignore[attr-defined]
        commune_code=row.commune_code,  # type: ignore[attr-defined]
        article_ref=row.article_ref,  # type: ignore[attr-defined]
        text=row.text,  # type: ignore[attr-defined]
        rank=rank,
    )


async def search_lexical(
    session: AsyncSession,
    query: str,
    *,
    commune_code: str | None = None,
    include_national: bool = True,
    document_type: DocumentType | None = None,
    limit: int = 20,
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
            Chunk.document_type,
            Chunk.legal_status,
            Chunk.commune_code,
            Document.title,
            Document.source_url,
            rank,
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.tsv.op("@@")(tsquery))
    )
    stmt = _scope_clause(
        stmt,
        commune_code=commune_code,
        include_national=include_national,
        document_type=document_type,
    )
    stmt = stmt.order_by(rank.desc()).limit(limit)

    rows = (await session.execute(stmt)).all()
    return [_row_to_chunk(row, float(row.rank)) for row in rows]


async def search_chunks(
    session: AsyncSession,
    query: str,
    *,
    commune_code: str | None = None,
    document_type: DocumentType | None = None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Backward-compatible exact-commune-match lexical search (no national
    fallback) — kept as-is for the original M3.4 retrieval-only eval and its
    regression tests (tests/test_retrieval.py). New parcel-scoped code
    should call `search_lexical`/`hybrid_search` directly, which include
    national legislation via `include_national=True`."""
    return await search_lexical(
        session,
        query,
        commune_code=commune_code,
        include_national=False,
        document_type=document_type,
        limit=limit,
    )


async def search_dense(
    session: AsyncSession,
    query_embedding: list[float],
    *,
    commune_code: str | None = None,
    include_national: bool = True,
    document_type: DocumentType | None = None,
    limit: int = 20,
) -> list[RetrievedChunk]:
    """pgvector cosine distance against the HNSW index
    (`ix_chunks_embedding_hnsw`). Chunks with no embedding yet (a fresh
    ingest before `make embed` has run) are excluded rather than sorted
    arbitrarily — `cosine_distance` against NULL is NULL, which the ORDER
    BY would otherwise place unpredictably."""
    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.article_ref,
            Chunk.text,
            Chunk.document_type,
            Chunk.legal_status,
            Chunk.commune_code,
            Document.title,
            Document.source_url,
            distance,
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.embedding.is_not(None))
    )
    stmt = _scope_clause(
        stmt,
        commune_code=commune_code,
        include_national=include_national,
        document_type=document_type,
    )
    stmt = stmt.order_by(distance.asc()).limit(limit)

    rows = (await session.execute(stmt)).all()
    # Cosine similarity (higher = better) is more intuitive to carry
    # downstream than distance (lower = better); RRF only uses rank order
    # anyway, but this keeps `RetrievedChunk.rank` meaning "higher is
    # better" consistently across lexical and dense results.
    return [_row_to_chunk(row, 1.0 - float(row.distance)) for row in rows]


def reciprocal_rank_fusion(
    ranked_lists: tuple[list[RetrievedChunk], ...], *, limit: int
) -> list[RetrievedChunk]:
    """Pure fusion step, factored out of `hybrid_search` so it's unit
    testable (tests/test_retrieval.py) without a live DB or embedding call
    — construct two small ranked lists by hand and assert the fused order.
    `score = sum(1 / (k + rank))` across whichever list(s) a chunk appears
    in (module docstring); mutates each returned chunk's `.rank` to the
    fused score, replacing its per-source rank/distance."""
    fused_scores: dict[uuid.UUID, float] = {}
    chunks_by_id: dict[uuid.UUID, RetrievedChunk] = {}
    for ranked_list in ranked_lists:
        for rank_zero_based, chunk in enumerate(ranked_list):
            fused_scores[chunk.chunk_id] = fused_scores.get(chunk.chunk_id, 0.0) + 1.0 / (
                _RRF_K + rank_zero_based + 1
            )
            chunks_by_id[chunk.chunk_id] = chunk

    ordered_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
    results = []
    for cid in ordered_ids[:limit]:
        chunk = chunks_by_id[cid]
        chunk.rank = fused_scores[cid]
        results.append(chunk)
    return results


async def hybrid_search(
    session: AsyncSession,
    query: str,
    *,
    commune_code: str | None = None,
    include_national: bool = True,
    document_type: DocumentType | None = None,
    candidates_per_source: int = 20,
    limit: int = 15,
) -> list[RetrievedChunk]:
    """Fuse lexical + dense candidates via Reciprocal Rank Fusion (see
    module docstring). Returns up to `limit` fused candidates — the caller
    (app/services/chatbot.py) reranks this set down further before
    generation (M3.1's explicit two-stage requirement).

    Degrades to lexical-only if the embedding API call itself fails (a
    real, live-encountered case in this environment — see
    app/services/embeddings.py's docstring on this account's tight
    gemini-embedding-001 quota) rather than failing the whole chat request:
    M2.1's "resilient, never aborts the run" principle applied to a live
    request path, not just a batch ingestion script. `search_lexical`
    alone is still a real, if partial, retrieval mechanism (see this
    module's own docstring on why lexical search matters independently of
    dense) — degraded quality, not a broken feature."""
    lexical = await search_lexical(
        session,
        query,
        commune_code=commune_code,
        include_national=include_national,
        document_type=document_type,
        limit=candidates_per_source,
    )

    try:
        query_embedding = await embed_query(query)
    except genai_errors.ClientError as exc:
        logger.warning("retrieval.dense_search_unavailable", error=str(exc)[:300])
        return reciprocal_rank_fusion((lexical,), limit=limit)

    dense = await search_dense(
        session,
        query_embedding,
        commune_code=commune_code,
        include_national=include_national,
        document_type=document_type,
        limit=candidates_per_source,
    )

    return reciprocal_rank_fusion((lexical, dense), limit=limit)
