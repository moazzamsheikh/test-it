"""M3.2/M3.3 — chatbot orchestration, against real ingested data but with
the LLM provider swapped for the deterministic `ExtractiveProvider` (see
app/services/llm/extractive.py) and the dense-embedding call monkeypatched
out. Both are deliberate: a real Gemini call is slow, costs quota, and
varies run to run — none of which is compatible with a fast, deterministic
test suite, and neither dependency is what these tests are actually
checking (refusal logic, citation-marker resolution, geospatial-fact
surfacing, conversation memory)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage
from app.models.enums import DocumentType, Language, LegalStatus
from app.models.provenance import Chunk, Document
from app.services.chatbot import (
    REFUSAL_TEXT,
    _build_sources,
    _extract_citations,
    _geospatial_facts,
    _NumberedSource,
    answer_question,
)
from app.services.llm.extractive import ExtractiveProvider
from app.services.parcels import get_parcel_detail

# A real ingested parcel used elsewhere in this test suite (test_report.py)
# — Schengen, a real PAG "MIX_v" zone with a real PAP QE reference.
_REAL_CADASTRAL_ID = "097D00240002285"


@pytest.fixture(autouse=True)
def _no_live_embedding_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dense retrieval needs a query embedding; the fixed vector below makes
    `search_dense` a real DB query (real pgvector cosine math) against
    whatever real chunks already have embeddings, just without hitting the
    live Gemini API on every test run."""

    async def _fake_embed_query(text: str) -> list[float]:
        del text
        return [1.0] + [0.0] * 1023

    monkeypatch.setattr("app.services.retrieval.embed_query", _fake_embed_query)


async def _insert_test_chunk(
    session: AsyncSession, *, text: str, commune_code: str | None = None
) -> uuid.UUID:
    document = Document(
        id=uuid.uuid4(),
        source_url=f"https://example.test/{uuid.uuid4()}",
        title="Loi de test sur les établissements",
        sha256=uuid.uuid4().hex,
        language=Language.fr,
        commune_code=commune_code,
        legal_status=LegalStatus.in_force,
        document_type=DocumentType.loi,
    )
    session.add(document)
    await session.flush()

    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=document.id,
        ordinal=0,
        article_ref="Art. 1",
        text=text,
        document_type=DocumentType.loi,
        legal_status=LegalStatus.in_force,
        commune_code=commune_code,
        language=Language.fr,
    )
    session.add(chunk)
    await session.flush()
    return document.id


async def test_refuses_when_nothing_relevant_is_retrieved(
    async_db_session: AsyncSession,
) -> None:
    response = await answer_question(
        async_db_session,
        session_id=f"test-{uuid.uuid4()}",
        message="xyzabc123 nonexistent gibberish query zzz with no possible match",
        cadastral_id=None,
        llm=ExtractiveProvider(),
    )

    assert response.refused is True
    assert response.answer == REFUSAL_TEXT
    assert response.citations == []


async def test_answers_and_cites_a_real_matching_chunk(async_db_session: AsyncSession) -> None:
    unique_term = f"zorbaflex{uuid.uuid4().hex[:8]}"
    await _insert_test_chunk(
        async_db_session, text=f"Cette disposition unique mentionne {unique_term} explicitement."
    )

    response = await answer_question(
        async_db_session,
        session_id=f"test-{uuid.uuid4()}",
        message=f"{unique_term}",
        cadastral_id=None,
        llm=ExtractiveProvider(),
    )

    assert response.refused is False
    assert len(response.citations) >= 1
    assert response.citations[0].document_title == "Loi de test sur les établissements"
    assert response.citations[0].article_ref == "Art. 1"
    assert "[1]" in response.answer


async def test_repealed_provision_never_surfaces_in_an_answer(
    async_db_session: AsyncSession,
) -> None:
    unique_term = f"zorbaflex{uuid.uuid4().hex[:8]}"
    document = Document(
        id=uuid.uuid4(),
        source_url=f"https://example.test/{uuid.uuid4()}",
        title="Loi abrogée",
        sha256=uuid.uuid4().hex,
        language=Language.fr,
        legal_status=LegalStatus.repealed,
        document_type=DocumentType.loi,
    )
    async_db_session.add(document)
    await async_db_session.flush()
    async_db_session.add(
        Chunk(
            id=uuid.uuid4(),
            document_id=document.id,
            ordinal=0,
            text=f"Disposition abrogée mentionnant {unique_term}.",
            document_type=DocumentType.loi,
            legal_status=LegalStatus.repealed,
            language=Language.fr,
        )
    )
    await async_db_session.flush()

    response = await answer_question(
        async_db_session,
        session_id=f"test-{uuid.uuid4()}",
        message=f"{unique_term}",
        cadastral_id=None,
        llm=ExtractiveProvider(),
    )

    # Excluded at the retrieval SQL level (app/services/retrieval.py) — the
    # only chunk that could answer this is repealed, so this must refuse,
    # not answer from a provision that no longer applies.
    assert response.refused is True


async def test_purely_geospatial_question_does_not_refuse(
    async_db_session: AsyncSession,
) -> None:
    """The real gap this guards against: a purely geospatial question about
    a real parcel with a real PAG zone must not refuse just because no
    document *text* happens to lexically/semantically match the question —
    even the extractive fallback (whose own top-2-sources behaviour, unlike
    a real LLM, doesn't guarantee it actually quotes a geospatial fact in
    this specific case) must still not trigger the refusal path."""
    response = await answer_question(
        async_db_session,
        session_id=f"test-{uuid.uuid4()}",
        message="xyzabc123 nonexistent gibberish query zzz with no text match",
        cadastral_id=_REAL_CADASTRAL_ID,
        llm=ExtractiveProvider(),
    )

    assert response.refused is False


async def test_real_parcel_offers_geospatial_facts_as_sources(
    async_db_session: AsyncSession,
) -> None:
    """Narrower than the end-to-end test above: checks the actual thing
    M3.3 requires directly — that a real parcel's M1/M2 facts are made
    available to the model as numbered sources at all — independent of
    which sources a specific provider chooses to quote in its answer."""
    parcel = await get_parcel_detail(async_db_session, _REAL_CADASTRAL_ID)
    assert parcel is not None

    _, _, geospatial_fact_count = await _build_sources(
        async_db_session, "irrelevant query text", parcel, ExtractiveProvider()
    )

    assert geospatial_fact_count > 0


async def test_geospatial_facts_have_distinct_meaningful_titles(
    async_db_session: AsyncSession,
) -> None:
    """Real UX gap caught by actual use, not anticipated: every geospatial
    fact used to share one identical, generic `document_title`
    ("Geospatial constraint (M1/M2 cadastral data)"), so a user reading two
    citations side by side in the same answer had no way to tell a PAG zone
    citation from an overlay citation without opening both links. Each fact
    now carries its own specific label."""
    parcel = await get_parcel_detail(async_db_session, _REAL_CADASTRAL_ID)
    assert parcel is not None

    facts = _geospatial_facts(parcel)

    assert len(facts) > 1  # this real parcel has more than one real fact
    titles = [f.document_title for f in facts]
    assert len(set(titles)) == len(titles), f"expected all-distinct titles, got {titles}"
    assert all(t.startswith("Geospatial data — ") for t in titles)


async def test_conversation_memory_persists_across_turns(async_db_session: AsyncSession) -> None:
    session_id = f"test-{uuid.uuid4()}"
    unique_term = f"zorbaflex{uuid.uuid4().hex[:8]}"
    await _insert_test_chunk(
        async_db_session, text=f"Cette disposition unique mentionne {unique_term} explicitement."
    )

    await answer_question(
        async_db_session,
        session_id=session_id,
        message=f"{unique_term}",
        cadastral_id=None,
        llm=ExtractiveProvider(),
    )
    # The point of this test is that the turn's exchange was actually
    # persisted and reloaded, not lost.
    rows = (
        (
            await async_db_session.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert [r.role for r in rows] == ["user", "assistant"]
    assert unique_term in rows[0].content


async def test_citation_marker_outside_source_range_is_dropped() -> None:
    """A citation-safety unit test on the extraction step itself: a marker
    the model wrote for a source number that doesn't exist must never
    resolve to anything, since ref_ids are only ever assigned to sources
    this platform actually retrieved."""
    sources = [
        _NumberedSource(
            ref_id=1,
            document_title="Real doc",
            article_ref=None,
            source_url="https://example.test",
            prompt_text="text",
        )
    ]
    citations = _extract_citations("This is grounded [1] but this is not [7].", sources)
    assert len(citations) == 1
    assert citations[0].ref_id == 1


def test_combined_bracket_citation_extracts_every_ref_id() -> None:
    """Real live regression: despite the system prompt asking for one
    number per bracket, a real Gemini response combined two into a single
    "[1, 2]" — a regex expecting exactly one digit group per bracket
    silently dropped the second citation rather than erroring, which is
    worse (an under-cited real source, not an obviously broken response)."""
    sources = [
        _NumberedSource(
            ref_id=1,
            document_title="Doc one",
            article_ref="Art. 3",
            source_url="https://example.test/1",
            prompt_text="text",
        ),
        _NumberedSource(
            ref_id=2,
            document_title="Doc two",
            article_ref="Art. 4",
            source_url="https://example.test/2",
            prompt_text="text",
        ),
    ]
    citations = _extract_citations("Both apply [1, 2].", sources)
    assert {c.ref_id for c in citations} == {1, 2}
