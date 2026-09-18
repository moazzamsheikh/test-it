"""M3.1 retrieval — lexical against real ingested chunks (not fixtures; see
EVAL.md for the full golden-set measurement), plus hermetic unit tests for
the pieces that don't need a live DB or a live embedding call: RRF fusion
and the legal_status/commune scoping rules."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DocumentType, Language, LegalStatus
from app.models.provenance import Chunk, Document
from app.services.retrieval import (
    RetrievedChunk,
    hybrid_search,
    reciprocal_rank_fusion,
    search_chunks,
    search_dense,
    search_lexical,
)


def _fake_chunk(chunk_id: uuid.UUID, rank: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        document_title="doc",
        source_url="https://example.test",
        document_type=DocumentType.loi,
        legal_status=LegalStatus.in_force,
        commune_code=None,
        article_ref=None,
        text="text",
        rank=rank,
    )


async def _insert_test_chunk(
    session: AsyncSession,
    *,
    text: str,
    legal_status: LegalStatus = LegalStatus.in_force,
    commune_code: str | None = None,
    embedding: list[float] | None = None,
) -> uuid.UUID:
    """A temp Source-less Document+Chunk for one test, inside the fixture's
    rolled-back transaction — never persisted past the test (see
    conftest.py)."""
    document = Document(
        id=uuid.uuid4(),
        source_url=f"https://example.test/{uuid.uuid4()}",
        title="Test document",
        sha256=uuid.uuid4().hex,
        language=Language.fr,
        commune_code=commune_code,
        legal_status=legal_status,
        document_type=DocumentType.loi,
    )
    session.add(document)
    await session.flush()

    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=document.id,
        ordinal=0,
        text=text,
        document_type=DocumentType.loi,
        legal_status=legal_status,
        commune_code=commune_code,
        language=Language.fr,
        embedding=embedding,
    )
    session.add(chunk)
    await session.flush()
    return chunk.id


async def test_natural_language_question_matches_real_article(
    async_db_session: AsyncSession,
) -> None:
    """A real natural-language question shares little exact vocabulary with
    its answer's formal legal text — AND-only matching (plainto_tsquery)
    returned nothing for nearly every real golden-set question until fixed
    to OR tokens together (see DECISIONS.md)."""
    results = await search_chunks(
        async_db_session,
        "Combien de classes existent pour les établissements classés ?",
        limit=5,
    )
    assert len(results) > 0
    assert any(r.document_title and "établissements classés" in r.document_title for r in results)


async def test_short_article_outranks_huge_unrelated_document(
    async_db_session: AsyncSession,
) -> None:
    """A real regression: before length normalization, an enormous
    PAG-document chunk (ingested as one giant blob, not per-article)
    outranked the short, genuinely relevant Findel servitude article
    purely by containing more raw text — not by being more relevant."""
    results = await search_chunks(
        async_db_session,
        "Quelles sont les servitudes liées aux radiophares d'alignement de l'aéroport de Findel ?",
        limit=1,
    )
    assert len(results) == 1
    assert results[0].document_title is not None
    assert "Aéroport et environs" in results[0].document_title


async def test_unmatched_query_returns_no_results(async_db_session: AsyncSession) -> None:
    results = await search_chunks(
        async_db_session, "xyzabc123 nonexistent gibberish query zzz", limit=5
    )
    assert results == []


async def test_real_identical_titled_bylaws_stay_commune_isolated(
    async_db_session: AsyncSession,
) -> None:
    """The brief's own literal example (M3.1: "a query about a parcel in
    Wiltz must not retrieve the Luxembourg City building bylaw"), against
    real data rather than synthetic rows — and a harder version of it: all
    8 communes' building bylaws share the EXACT SAME document title
    ("Règlement sur les bâtisses, les voies publiques et les sites"), so a
    title-only check could never catch cross-commune leakage here. Real,
    confirmed fact: only Differdange's (admin_commune_code '0202') bylaw
    has a "pompes à chaleur" (heat pump) article at all — Dudelange's
    ('0203') bylaw genuinely has no such article, so this isn't a
    coincidence of which commune happens to rank first."""
    differdange_results = await search_lexical(
        async_db_session, "pompes à chaleur", commune_code="0202", include_national=False
    )
    assert any(r.article_ref == "Art. 15" for r in differdange_results)

    dudelange_results = await search_lexical(
        async_db_session, "pompes à chaleur", commune_code="0203", include_national=False
    )
    assert all(r.commune_code != "0202" for r in dudelange_results)


# --- M3.2: repealed/superseded provisions must never be a retrieval candidate ---


async def test_repealed_chunk_excluded_from_lexical_search(async_db_session: AsyncSession) -> None:
    unique_term = f"zorbaflex{uuid.uuid4().hex[:8]}"
    await _insert_test_chunk(
        async_db_session,
        text=f"Article unique mentionnant {unique_term} dans un texte abrogé.",
        legal_status=LegalStatus.repealed,
    )

    results = await search_lexical(async_db_session, unique_term, include_national=False)

    assert results == []


async def test_in_force_chunk_is_retrievable(async_db_session: AsyncSession) -> None:
    unique_term = f"zorbaflex{uuid.uuid4().hex[:8]}"
    chunk_id = await _insert_test_chunk(
        async_db_session,
        text=f"Article unique mentionnant {unique_term} dans un texte en vigueur.",
        legal_status=LegalStatus.in_force,
    )

    results = await search_lexical(async_db_session, unique_term, include_national=False)

    assert [r.chunk_id for r in results] == [chunk_id]


# --- M3.1: metadata filtering — a Wiltz question must not surface a
# different commune's bylaw, but must still surface national legislation ---


async def test_commune_scoped_search_excludes_other_communes(
    async_db_session: AsyncSession,
) -> None:
    unique_term = f"zorbaflex{uuid.uuid4().hex[:8]}"
    await _insert_test_chunk(
        async_db_session,
        text=f"Règlement communal mentionnant {unique_term}.",
        commune_code="9999",  # a commune code that isn't the one queried
    )

    results = await search_lexical(
        async_db_session, unique_term, commune_code="0101", include_national=False
    )

    assert results == []


async def test_commune_scoped_search_still_includes_national_legislation(
    async_db_session: AsyncSession,
) -> None:
    unique_term = f"zorbaflex{uuid.uuid4().hex[:8]}"
    await _insert_test_chunk(
        async_db_session,
        text=f"Loi nationale mentionnant {unique_term}.",
        commune_code=None,  # national legislation — applies everywhere
    )

    results = await search_lexical(
        async_db_session, unique_term, commune_code="0101", include_national=True
    )

    assert len(results) == 1


# --- M3.1: dense retrieval (pgvector cosine) ---


async def test_dense_search_ranks_by_cosine_similarity(async_db_session: AsyncSession) -> None:
    close_vector = [1.0] + [0.0] * 1023
    far_vector = [0.0, 1.0] + [0.0] * 1022
    close_id = await _insert_test_chunk(
        async_db_session, text="close chunk", embedding=close_vector
    )
    far_id = await _insert_test_chunk(async_db_session, text="far chunk", embedding=far_vector)

    # `far_vector` is exactly orthogonal to the query — the worst possible
    # cosine score — so as the real embedded corpus grows (see
    # ingestion/embed_chunks.py's ongoing backfill), it legitimately ranks
    # behind more and more real chunks. A limit comfortably above the whole
    # corpus size keeps this test robust to that growth rather than
    # accidentally re-testing "how big is the corpus right now".
    results = await search_dense(async_db_session, close_vector, include_national=True, limit=5000)
    ids_in_order = [r.chunk_id for r in results]

    assert close_id in ids_in_order
    assert far_id in ids_in_order
    assert ids_in_order.index(close_id) < ids_in_order.index(far_id)


async def test_dense_search_excludes_unembedded_chunks(async_db_session: AsyncSession) -> None:
    unembedded_id = await _insert_test_chunk(
        async_db_session, text="never embedded", embedding=None
    )

    results = await search_dense(
        async_db_session, [1.0] + [0.0] * 1023, include_national=True, limit=1000
    )

    assert unembedded_id not in {r.chunk_id for r in results}


# --- M3.1: Reciprocal Rank Fusion (pure, no DB/network) ---


def test_rrf_favours_a_chunk_ranked_in_both_lists() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    lexical = [_fake_chunk(a, 3.0), _fake_chunk(b, 1.0)]
    dense = [_fake_chunk(b, 0.9), _fake_chunk(c, 0.8)]

    fused = reciprocal_rank_fusion((lexical, dense), limit=10)

    # b appears first in both lists' relative contribution (rank 1 in
    # lexical, rank 0 in dense) — its fused score must beat a chunk that
    # only appears in one list at a similarly-good rank.
    assert fused[0].chunk_id == b


def test_rrf_respects_limit() -> None:
    chunks = [_fake_chunk(uuid.uuid4(), float(i)) for i in range(5)]
    fused = reciprocal_rank_fusion((chunks,), limit=2)
    assert len(fused) == 2


def test_rrf_empty_input_returns_empty() -> None:
    assert reciprocal_rank_fusion(([], []), limit=10) == []


@pytest.mark.parametrize("limit", [1, 3])
def test_rrf_single_list_preserves_relative_order(limit: int) -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ranked = [_fake_chunk(a, 3.0), _fake_chunk(b, 2.0), _fake_chunk(c, 1.0)]
    fused = reciprocal_rank_fusion((ranked,), limit=limit)
    assert [c.chunk_id for c in fused] == [a, b, c][:limit]


# --- M2.1 resilience, applied to a live request path ---


async def test_hybrid_search_degrades_to_lexical_when_embedding_api_unavailable(
    async_db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real, live-encountered case in this environment (see
    app/services/embeddings.py): the embedding API's own quota can be
    exhausted at request time, not just during a batch backfill. A chat
    request must degrade to lexical-only, not 500."""
    from google.genai import errors as genai_errors

    async def _raise_quota_exhausted(text: str) -> list[float]:
        del text
        raise genai_errors.ClientError(429, {"error": {"message": "quota exhausted"}}, None)

    monkeypatch.setattr("app.services.retrieval.embed_query", _raise_quota_exhausted)

    unique_term = f"zorbaflex{uuid.uuid4().hex[:8]}"
    await _insert_test_chunk(
        async_db_session, text=f"Article unique mentionnant {unique_term} en vigueur."
    )

    results = await hybrid_search(async_db_session, unique_term, include_national=False)

    assert len(results) == 1
