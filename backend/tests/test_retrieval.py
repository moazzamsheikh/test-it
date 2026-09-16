"""M3.1 minimal lexical retrieval — against real ingested chunks, not
fixtures. See EVAL.md for the full golden-set measurement; these are
narrower regression tests for the two real bugs caught while building
that eval (AND-only matching, unnormalized document-length ranking)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval import search_chunks


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
