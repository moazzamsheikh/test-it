"""Real Gemini-backed `LLMProvider`. The only implementation with actual
network calls — `extractive.py` is the no-API-key fallback used in tests
and as a safety net (see its own docstring)."""

from __future__ import annotations

import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services.llm.base import ChatTurn, SourcePassage

logger = structlog.get_logger(__name__)

# Gemini's role vocabulary is "user"/"model", not "user"/"assistant" — a
# real, easy-to-miss mismatch confirmed against the SDK's own examples
# before writing this, not guessed.
_ROLE_MAP = {"user": "user", "assistant": "model"}


class _RelevanceScores(BaseModel):
    scores: list[float]


def _is_rate_limit_error(exc: BaseException) -> bool:
    return isinstance(exc, genai_errors.ClientError) and exc.code == 429


class GeminiProvider:
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=settings.gemini_api_key)

    # Fast-fail on purpose, not patient — this is a live chat request, and
    # app/services/chatbot.py's `_complete_resilient`/`_rerank_resilient`
    # are the real safety net (falls back to ExtractiveProvider for the
    # turn). A real bug this fixes: with a patient multi-minute retry
    # budget here, a 429 would exhaust ALL of it before the outer fallback
    # ever got a chance, leaving a live user staring at "Thinking..." for
    # minutes — caught by manual browser testing, not anticipated (the
    # brief's own M2.1 "resilient" pattern was already applied to the
    # embedding path's live/patient split; this is the same fix applied to
    # generation/reranking, one layer up).
    @retry(
        retry=retry_if_exception(_is_rate_limit_error),
        wait=wait_exponential(multiplier=3, min=3, max=6),
        stop=stop_after_attempt(2),
        reraise=True,
    )
    async def complete(
        self,
        *,
        system: str,
        history: list[ChatTurn],
        user_message: str,
        sources: list[SourcePassage],
    ) -> str:
        contents = [
            types.Content(role=_ROLE_MAP[turn.role], parts=[types.Part(text=turn.content)])
            for turn in history
        ]
        sources_block = (
            "\n\n".join(
                f"[{s.ref_id}] {s.document_title}"
                + (f", {s.article_ref}" if s.article_ref else "")
                + f":\n{s.text}"
                for s in sources
            )
            if sources
            else "(no relevant sources retrieved)"
        )
        final_turn = f"Sources:\n{sources_block}\n\nQuestion: {user_message}"
        contents.append(types.Content(role="user", parts=[types.Part(text=final_turn)]))

        response = await self._client.aio.models.generate_content(
            model=settings.gemini_model,
            # Same mypy/SDK-overload invariance issue as
            # app/services/embeddings.py — `list[Content]` is a valid,
            # documented input, just not matched by the strict overload set.
            contents=contents,  # type: ignore[arg-type]
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.1),
        )
        return response.text or ""

    # Fast-fail on purpose, not patient — this is a live chat request, and
    # app/services/chatbot.py's `_complete_resilient`/`_rerank_resilient`
    # are the real safety net (falls back to ExtractiveProvider for the
    # turn). A real bug this fixes: with a patient multi-minute retry
    # budget here, a 429 would exhaust ALL of it before the outer fallback
    # ever got a chance, leaving a live user staring at "Thinking..." for
    # minutes — caught by manual browser testing, not anticipated (the
    # brief's own M2.1 "resilient" pattern was already applied to the
    # embedding path's live/patient split; this is the same fix applied to
    # generation/reranking, one layer up).
    @retry(
        retry=retry_if_exception(_is_rate_limit_error),
        wait=wait_exponential(multiplier=3, min=3, max=6),
        stop=stop_after_attempt(2),
        reraise=True,
    )
    async def score_relevance(self, *, query: str, candidates: list[str]) -> list[float]:
        """LLM-based reranking (M3.1, justified in reranking.py): asks the
        model for a strict JSON array of per-candidate relevance scores,
        constrained via `response_schema` — not free text parsed with
        regex, which would be one more place this could silently
        misparse."""
        if not candidates:
            return []

        numbered = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(candidates))
        prompt = (
            f"Question: {query}\n\n"
            f"Candidate passages, numbered [0]..[{len(candidates) - 1}]:\n\n{numbered}\n\n"
            "For EACH candidate, in order, score 0.0-1.0 how relevant it is to answering "
            "the question directly and specifically. Return exactly "
            f"{len(candidates)} scores, one per candidate, in the same order."
        )

        response = await self._client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=_RelevanceScores,
            ),
        )

        try:
            parsed = _RelevanceScores.model_validate_json(response.text or "")
        except ValidationError:
            logger.warning("gemini.rerank_parse_failed", raw=response.text)
            parsed = None

        if parsed is None or len(parsed.scores) != len(candidates):
            # Real, disclosed fallback (see reranking.py): rather than crash
            # the chat turn over a malformed rerank response, fall back to
            # the fused RRF order already computed upstream — a linearly
            # decaying score preserves that order without pretending it's
            # an LLM judgement.
            logger.warning(
                "gemini.rerank_length_mismatch",
                expected=len(candidates),
                got=len(parsed.scores) if parsed else None,
            )
            n = len(candidates)
            return [1.0 - i / n for i in range(n)]

        return parsed.scores
