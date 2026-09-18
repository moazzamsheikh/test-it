"""LLM provider abstraction (brief §4: "abstract it behind an interface —
we must be able to swap models without touching business logic").

Two capabilities, both used by `app/services/chatbot.py`:
- `complete`: grounded generation for the final chat answer.
- `score_relevance`: LLM-based reranking of retrieval candidates (M3.1 —
  "Cross-encoder or LLM-based, your call, justified"; see
  `app/services/reranking.py` for the justification).

`complete` takes `sources` as a structured, numbered list rather than a
pre-flattened prompt string — a deliberate interface choice, not
incidental: it makes citation-safety structural. A provider can only ever
cite `ref_id`s that exist in this exact list (`app/services/chatbot.py`
discards any citation marker outside that range before it reaches the
API response), and a provider with no LLM behind it at all (see
`extractive.py`) can still produce a real, grounded, testable answer by
just assembling these passages directly — no free-text parsing of a
flattened prompt required."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class SourcePassage(BaseModel):
    ref_id: int  # 1-based citation number the answer should reference as [n]
    document_title: str
    article_ref: str | None
    text: str


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        system: str,
        history: list[ChatTurn],
        user_message: str,
        sources: list[SourcePassage],
    ) -> str:
        """Grounded completion: answer `user_message` using ONLY `sources`,
        citing each as `[ref_id]`. Returns the raw answer text; citation
        markers are extracted and resolved by the caller."""
        ...

    async def score_relevance(self, *, query: str, candidates: list[str]) -> list[float]:
        """One relevance score in [0, 1] per candidate, same order as
        input — used to rerank a fused retrieval candidate set."""
        ...
