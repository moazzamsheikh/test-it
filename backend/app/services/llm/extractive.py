"""No-API-key fallback `LLMProvider`. Two real uses, not a toy:

1. Tests exercise the full retrieval -> rerank -> "generation" -> citation
   pipeline deterministically, with no network call and no LLM API cost —
   `app/services/chatbot.py`'s refusal/citation-extraction logic needs to
   be tested against a completion whose exact text is known in advance,
   which a real LLM can never guarantee turn to turn.
2. A real safety net: if `GEMINI_API_KEY` is unset or the provider factory
   can't reach the API, the chatbot still returns a grounded, cited answer
   — assembled directly from the retrieved passages — rather than a 500 or
   a silent empty response. It cannot paraphrase, synthesise across
   sources, or judge ambiguity the way a real LLM can; it is intentionally
   plain about that in its own output.
"""

from __future__ import annotations

from app.services.llm.base import ChatTurn, SourcePassage
from app.services.retrieval import meaningful_tokens

_MAX_QUOTE_CHARS = 600


class ExtractiveProvider:
    async def complete(
        self,
        *,
        system: str,
        history: list[ChatTurn],
        user_message: str,
        sources: list[SourcePassage],
    ) -> str:
        del system, history, user_message  # unused — no LLM to condition on them
        if not sources:
            return "I don't have a source for that."

        lines = [
            "[Extractive mode — no generative LLM configured; this quotes the "
            "top retrieved source(s) verbatim rather than composing an answer.]",
            "",
        ]
        for s in sources[:2]:
            citation = f"[{s.ref_id}] {s.document_title}"
            if s.article_ref:
                citation += f", {s.article_ref}"
            quote = s.text.strip()[:_MAX_QUOTE_CHARS]
            if len(s.text.strip()) > _MAX_QUOTE_CHARS:
                quote += "…"
            lines.append(f"{citation}: {quote}")
        return "\n\n".join(lines)

    async def score_relevance(self, *, query: str, candidates: list[str]) -> list[float]:
        """Real, if crude, relevance signal — NOT a passthrough. A blind
        passthrough (score every candidate by its incoming order) was the
        first version of this and had a genuine bug, caught while writing
        tests, not in production: dense retrieval unconditionally returns
        *something* as "nearest by cosine distance" even for a query with
        no real match in the corpus, and a passthrough score would always
        rank that noise candidate's score as if it were the top result —
        silently defeating M3.2's refusal guarantee the one time this
        fallback provider would matter most (the real provider being
        unavailable). Word-overlap against `meaningful_tokens` (the same
        stopword-aware tokenizer lexical search itself uses) gives a
        genuine, if simple, signal: a candidate sharing none of the
        query's real content words scores nowhere near
        `chatbot._RELEVANCE_THRESHOLD`, and one built specifically to
        answer the question scores well above it."""
        query_tokens = meaningful_tokens(query)
        if not query_tokens:
            return [0.0 for _ in candidates]
        scores = []
        for text in candidates:
            overlap = query_tokens & meaningful_tokens(text)
            scores.append(len(overlap) / len(query_tokens))
        return scores
