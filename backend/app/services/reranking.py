"""M3.1 reranking — LLM-based, not a cross-encoder.

The brief explicitly allows either ("Cross-encoder or LLM-based, your call,
justified"). This is an environment-forced choice, not a stylistic one:
every standard cross-encoder path (`sentence-transformers`, `fastembed`)
needs `torch` or `onnxruntime`, and neither publishes a wheel for this
environment's Python 3.14 (verified — see app/services/embeddings.py).
Reusing the same Gemini provider already required for generation avoids
adding a second, currently-uninstallable ML dependency for a real,
verified reason.

Trade-off, disclosed rather than hidden: an LLM-based rerank costs one
extra API call and network round-trip per chat turn, and is less
deterministic run-to-run than a fixed cross-encoder's weights would be. At
this corpus's scale and a chat (not bulk-batch) latency budget, that's an
acceptable cost for materially better relevance ordering than the fused
RRF list alone — see EVAL.md for the measured before/after.
"""

from __future__ import annotations

from app.services.llm.base import LLMProvider
from app.services.retrieval import RetrievedChunk

# Passed to the LLM for scoring only (a fast relevance judgement, not the
# final answer) — kept short to bound prompt size/latency when reranking
# up to ~15-20 fused candidates in one call. The *full* chunk text is what
# actually goes to generation afterwards (app/services/chatbot.py), so
# nothing here limits what the final answer can quote or cite.
_RERANK_SNIPPET_CHARS = 1500


async def rerank(
    llm: LLMProvider,
    query: str,
    candidates: list[RetrievedChunk],
    *,
    top_k: int,
) -> list[RetrievedChunk]:
    if not candidates:
        return []

    scores = await llm.score_relevance(
        query=query, candidates=[c.text[:_RERANK_SNIPPET_CHARS] for c in candidates]
    )
    scored = list(zip(candidates, scores, strict=True))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    for chunk, score in scored:
        chunk.rank = score
    return [chunk for chunk, _ in scored[:top_k]]
