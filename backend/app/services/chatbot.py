"""M3.2/M3.3 — grounded, parcel-scoped chat over the ingested corpus.

Pipeline per turn: hybrid retrieval (M3.1, retrieval.py) -> LLM rerank
(reranking.py) -> refusal check -> numbered-source assembly (retrieved
text chunks + M1/M2 geospatial facts for the selected parcel) -> grounded
completion (llm/) -> citation-marker extraction, resolved only against the
exact numbered-source list, never trusted freeform from the model.

Refusal (M3.2 — "a confident hallucinated answer scores worse than a
refusal") is a deterministic, pre-generation check, not something asked of
the LLM's own judgement: the answer is the literal brief-specified refusal
string, with the LLM never even called, unless EITHER the reranked top
text-chunk score clears `_RELEVANCE_THRESHOLD` OR the selected parcel has
at least one M1/M2 geospatial fact to surface. That "OR", not "AND", is
deliberate: a purely geospatial question ("what PAG zone is this parcel
in?") can have zero relevant retrieved *text* yet be fully answerable from
cadastral data alone (M3.3) — checking only the text score would wrongly
refuse it. This is reliable specifically because it doesn't depend on the
model choosing to say so — the one thing M3.2 warns is exactly the failure
mode to avoid.

Never-cite-a-repealed-provision (M3.2) is enforced twice, not once:
`retrieval.py` excludes `repealed`/`superseded` chunks at the SQL level
(never a retrieval candidate at all), and any `unknown`/`draft` chunk that
IS retrieved is annotated in the prompt so the model hedges rather than
asserts it as settled current law (see `_annotate_status`).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from google.genai import errors as genai_errors
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage
from app.models.enums import LegalStatus
from app.schemas.chat import ChatCitation, ChatResponse
from app.schemas.pag import PagZoneMatch, PapNqZoneMatch, PapQeZoneMatch
from app.schemas.parcel import OverlayConstraint, ParcelDetail
from app.services.llm import ChatTurn, LLMProvider, SourcePassage, get_llm_provider
from app.services.llm.extractive import ExtractiveProvider
from app.services.pag_zoning import derive_pag_zone_label
from app.services.parcels import get_parcel_detail
from app.services.reranking import rerank
from app.services.retrieval import RetrievedChunk, hybrid_search

logger = structlog.get_logger(__name__)

REFUSAL_TEXT = "I don't have a source for that."

# Same resilience principle as app/services/embeddings.py/retrieval.py,
# applied to the generation/rerank calls: a real, live-encountered Gemini
# failure mode ("503 UNAVAILABLE — model experiencing high demand") was
# caught propagating as an unhandled exception all the way to a raw 500 —
# which, confusingly, presents to a browser as a CORS error (no CORS
# headers get attached to a response that never reaches the middleware
# cleanly), not as the real upstream failure it is. Falling back to
# `ExtractiveProvider` for just that call keeps the turn answering (in
# extractive mode, honestly labelled) instead of failing the whole request.
_RESILIENCE_FALLBACK = ExtractiveProvider()


async def _rerank_resilient(
    llm: LLMProvider, query: str, candidates: list[RetrievedChunk], *, top_k: int
) -> list[RetrievedChunk]:
    try:
        return await rerank(llm, query, candidates, top_k=top_k)
    except (genai_errors.ServerError, genai_errors.ClientError) as exc:
        logger.warning("chatbot.rerank_failed_falling_back", error=str(exc)[:300])
        return await rerank(_RESILIENCE_FALLBACK, query, candidates, top_k=top_k)


async def _complete_resilient(
    llm: LLMProvider,
    *,
    system: str,
    history: list[ChatTurn],
    user_message: str,
    sources: list[SourcePassage],
) -> str:
    try:
        return await llm.complete(
            system=system, history=history, user_message=user_message, sources=sources
        )
    except (genai_errors.ServerError, genai_errors.ClientError) as exc:
        logger.warning("chatbot.complete_failed_falling_back", error=str(exc)[:300])
        return await _RESILIENCE_FALLBACK.complete(
            system=system, history=history, user_message=user_message, sources=sources
        )


# The LLM reranker scores 0.0-1.0 "relevance to answering the question
# directly and specifically" (see reranking.py's prompt). Below this, the
# top candidate is judged too weak to ground an answer on — chosen by
# hand-testing against the golden set's one deliberately-unanswerable
# question plus several real answerable ones (see EVAL.md for the measured
# effect); not derived from a formula, disclosed as a tuned constant.
_RELEVANCE_THRESHOLD = 0.35

_CANDIDATES_PER_SOURCE = 20
_FUSED_LIMIT = 15
_RERANK_TOP_K = 5

# How many prior turns (user+assistant pairs) of real conversation memory
# to replay into the prompt (M3.3). Bounded so a long session doesn't grow
# the prompt unboundedly — a real, disclosed limit, not unlimited memory.
_HISTORY_TURNS = 6

# Matches both "[1]" and "[1, 2]" / "[1,2]" — despite the system prompt
# asking for one number per bracket, a real live response combined two
# into a single "[1, 2]" bracket (caught by manual testing, not assumed):
# a regex expecting exactly one digit group would silently drop the second
# citation rather than error, which is worse — an under-cited real source,
# not an obviously broken response.
_CITATION_MARKER_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

_SYSTEM_PROMPT = """You are a regulatory assistant for architects working on a specific \
cadastral parcel in Luxembourg. Answer ONLY using the numbered sources provided in each \
turn — never from general knowledge of Luxembourg law, and never by inventing a source, \
article, or URL that isn't in the list.

Rules, non-negotiable:
1. Every factual claim must carry an inline citation to the source(s) it came from, \
formatted as [n] using that source's number.
2. If the sources don't actually answer the question, say plainly that you don't have a \
source for that rather than guessing or answering from general knowledge.
3. If a source is marked "[STATUS NOT INDEPENDENTLY VERIFIED]" or "[DRAFT / NOT YET IN \
FORCE]", say so explicitly when you rely on it — never present it as settled current law.
4. If two sources conflict, or a rule's wording is genuinely ambiguous, say so explicitly \
("the rule says X, but Y is ambiguous because...") rather than picking one confident answer.
5. Answer in the same language the question was asked in (French, German, Luxembourgish, \
or English) — a citation number [n] and the source titles may stay as given.
6. Sources titled "Geospatial data — ..." came from this platform's own cadastral/GIS data \
(M1/M2), not a text document — cite them the same way, as [n]."""


@dataclass
class _NumberedSource:
    ref_id: int
    document_title: str
    article_ref: str | None
    source_url: str
    prompt_text: str  # what's actually shown to the LLM (may carry a status annotation)


def _annotate_status(chunk: RetrievedChunk) -> str:
    if chunk.legal_status == LegalStatus.draft:
        return f"[DRAFT / NOT YET IN FORCE] {chunk.text}"
    if chunk.legal_status == LegalStatus.unknown:
        return f"[STATUS NOT INDEPENDENTLY VERIFIED] {chunk.text}"
    return chunk.text


def _geospatial_facts(parcel: ParcelDetail) -> list[_NumberedSource]:
    """M3.3 — 'answers surface the geospatial constraints from M1 alongside
    the textual ones': turns the already-computed M1.4 overlay constraints
    and M2 PAG/PAP zoning into the same numbered-source shape as a
    retrieved text chunk, so the model cites them identically (as [n]) and
    the API response's citation list can point a client straight at the
    parcel-detail data it already renders, not just document URLs."""
    facts: list[_NumberedSource] = []

    # A per-fact, human-meaningful `document_title` — not a repeated generic
    # "Geospatial constraint" label, which real usage showed makes every
    # citation in a multi-fact answer look identical (a user can't tell a
    # PAG zone citation from an overlay citation without opening each link).
    # Prefixed with "Geospatial data —" so it's still visually distinct from
    # a real text-document citation at a glance, per the system prompt's own
    # rule 6.
    def add(document_title: str, text: str, source_url: str) -> None:
        facts.append(
            _NumberedSource(
                ref_id=0,  # assigned by the caller once merged with text chunks
                document_title=f"Geospatial data — {document_title}",
                article_ref=None,
                source_url=source_url,
                prompt_text=text,
            )
        )

    zone: PagZoneMatch
    for zone in parcel.pag_zoning.pag_zones:
        # The raw category code ("FOR", "MIX_u") means nothing to an
        # architect on its own — a real user-facing gap, caught by actual
        # use: the chatbot cited "PAG zone 'FOR'" with no explanation of
        # what "FOR" means, even though the real written-part document
        # (already fetched) states it in plain language. Reuses the same
        # extraction M4's report already relies on, not a second lookup.
        human_label = derive_pag_zone_label(zone.category, zone.document)
        label = f"PAG zone '{zone.category}'"
        if human_label != zone.category:
            label += f" ({human_label})"
        if zone.genre:
            label += f" — {zone.genre}"
        url = zone.document.source_url if zone.document else ""
        if url:
            add(label, f"This parcel is classified under {label} in the commune's PAG.", url)

    qe: PapQeZoneMatch
    for qe in parcel.pag_zoning.pap_qe_zones:
        url = qe.written_document.source_url if qe.written_document else ""
        if url:
            add(
                "PAP 'Quartier Existant' (QE) perimeter",
                "This parcel lies within a PAP 'Quartier Existant' (QE) perimeter.",
                url,
            )

    nq: PapNqZoneMatch
    for nq in parcel.pag_zoning.pap_nq_zones:
        url = nq.written_document.source_url if nq.written_document else ""
        coeffs = ", ".join(
            f"{name}={value}"
            for name, value in (
                ("COS max", nq.cos_max),
                ("CUS max", nq.cus_max),
                ("CSS max", nq.css_max),
                ("DL max", nq.dl_max),
            )
            if value is not None
        )
        if url:
            text = "This parcel lies within a PAP 'Nouveau Quartier' (NQ) zone"
            if coeffs:
                text += f", with planning coefficients {coeffs}"
            add("PAP 'Nouveau Quartier' (NQ) zone", text + ".", url)

    constraint: OverlayConstraint
    for constraint in parcel.constraints:
        if not constraint.intersects:
            continue
        add(
            f"overlay — {constraint.label}",
            f"Regulatory overlay '{constraint.label}' applies to this parcel.",
            constraint.source_url,
        )

    return facts


async def _build_sources(
    session: AsyncSession, question: str, parcel: ParcelDetail | None, llm: LLMProvider
) -> tuple[list[_NumberedSource], list[RetrievedChunk], int]:
    """Returns (numbered sources, reranked text chunks, geospatial fact
    count) — kept separate rather than folded into one list/score because
    refusal (M3.2) must not fire just because no *text* document matched: a
    purely geospatial question ("what PAG zone is this parcel in?") can be
    fully answered from M1/M2 facts alone with zero relevant retrieved
    text, and refusing that would be wrong, not cautious."""
    admin_commune_code = parcel.admin_commune_code if parcel else None

    fused = await hybrid_search(
        session,
        question,
        commune_code=admin_commune_code,
        include_national=True,
        candidates_per_source=_CANDIDATES_PER_SOURCE,
        limit=_FUSED_LIMIT,
    )
    reranked = await _rerank_resilient(llm, question, fused, top_k=_RERANK_TOP_K) if fused else []

    sources = [
        _NumberedSource(
            ref_id=0,
            document_title=chunk.document_title or "(untitled document)",
            article_ref=chunk.article_ref,
            source_url=chunk.source_url,
            prompt_text=_annotate_status(chunk),
        )
        for chunk in reranked
    ]
    geospatial_facts = _geospatial_facts(parcel) if parcel is not None else []
    sources.extend(geospatial_facts)

    for i, s in enumerate(sources, start=1):
        s.ref_id = i

    return sources, reranked, len(geospatial_facts)


def _extract_citations(answer_text: str, sources: list[_NumberedSource]) -> list[ChatCitation]:
    by_ref = {s.ref_id: s for s in sources}
    seen: set[int] = set()
    citations: list[ChatCitation] = []
    for match in _CITATION_MARKER_RE.finditer(answer_text):
        for ref_id_str in match.group(1).split(","):
            ref_id = int(ref_id_str.strip())
            # Never resolve a marker the model invented outside the real
            # numbered-source range — this is the structural guardrail
            # against a hallucinated citation surviving into the response.
            if ref_id in seen or ref_id not in by_ref:
                continue
            seen.add(ref_id)
            s = by_ref[ref_id]
            citations.append(
                ChatCitation(
                    ref_id=ref_id,
                    document_title=s.document_title,
                    article_ref=s.article_ref,
                    source_url=s.source_url,
                )
            )
    return citations


async def _load_history(session: AsyncSession, session_id: str) -> list[ChatTurn]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(_HISTORY_TURNS * 2)
    )
    rows = list(reversed((await session.execute(stmt)).scalars().all()))
    return [ChatTurn(role=row.role, content=row.content) for row in rows]


async def answer_question(
    session: AsyncSession,
    *,
    session_id: str,
    message: str,
    cadastral_id: str | None,
    llm: LLMProvider | None = None,
) -> ChatResponse:
    """`llm` is injectable (defaults to the configured provider via the
    factory) so tests can pass a deterministic `ExtractiveProvider` — see
    tests/test_chatbot.py — without needing a real network call or the
    real provider's inherent run-to-run variability."""
    llm = llm or get_llm_provider()
    parcel = await get_parcel_detail(session, cadastral_id) if cadastral_id else None

    history = await _load_history(session, session_id)
    sources, reranked, geospatial_fact_count = await _build_sources(session, message, parcel, llm)

    top_text_score = reranked[0].rank if reranked else 0.0
    has_grounding = top_text_score >= _RELEVANCE_THRESHOLD or geospatial_fact_count > 0
    if not has_grounding:
        answer_text = REFUSAL_TEXT
        citations: list[ChatCitation] = []
        refused = True
    else:
        answer_text = await _complete_resilient(
            llm,
            system=_SYSTEM_PROMPT,
            history=history,
            user_message=message,
            sources=[
                SourcePassage(
                    ref_id=s.ref_id,
                    document_title=s.document_title,
                    article_ref=s.article_ref,
                    text=s.prompt_text,
                )
                for s in sources
            ],
        )
        citations = _extract_citations(answer_text, sources)
        refused = answer_text.strip() == REFUSAL_TEXT

    session.add_all(
        [
            ChatMessage(
                id=uuid.uuid4(),
                session_id=session_id,
                parcel_cadastral_id=cadastral_id,
                role="user",
                content=message,
                created_at=datetime.now(UTC),
            ),
            ChatMessage(
                id=uuid.uuid4(),
                session_id=session_id,
                parcel_cadastral_id=cadastral_id,
                role="assistant",
                content=answer_text,
                created_at=datetime.now(UTC),
            ),
        ]
    )
    await session.commit()

    return ChatResponse(
        answer=answer_text,
        citations=citations,
        refused=refused,
        parcel_cadastral_id=cadastral_id,
    )
