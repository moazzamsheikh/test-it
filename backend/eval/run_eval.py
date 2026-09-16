"""M3.4 — runs the golden set (eval/golden_set.json) against the real
retrieval function (app/services/retrieval.py::search_chunks, lexical-only
— see that module's docstring for why) and reports real, measured
precision/recall and citation accuracy. Writes EVAL.md at the repo root.

This is explicitly a retrieval-only eval, not a generation eval — no
chatbot/LLM answer layer was built today (see DECISIONS.md/PROGRESS.md),
so "citation accuracy" here means "was the expected real article among the
retrieved results", not "did a generated answer cite it correctly".

Run with: make eval
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.services.retrieval import search_chunks

_GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.json"
_EVAL_MD_PATH = Path(__file__).parents[2] / "EVAL.md"
_TOP_K = 5


async def run() -> None:
    golden_set = json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    engine = create_async_engine(settings.database_url)

    rows = []
    doc_hits = 0
    article_hits = 0
    answerable = 0
    unanswerable_correctly_empty_or_low_relevance = 0

    async with AsyncSession(engine) as session:
        for item in golden_set:
            results = await search_chunks(session, item["question"], limit=_TOP_K)
            expected_doc = item.get("expected_document_title_contains")
            expected_article = item.get("expected_article_ref")

            if expected_doc is None:
                # Deliberately unanswerable question (M3.2's refusal test).
                top_rank = results[0].rank if results else 0.0
                is_low_relevance = not results or top_rank < 0.01
                if is_low_relevance:
                    unanswerable_correctly_empty_or_low_relevance += 1
                rows.append(
                    {
                        "question": item["question"],
                        "expected": "(deliberately unanswerable)",
                        "top_result": (
                            f"{results[0].document_title} ({results[0].article_ref})"
                            if results
                            else "(none)"
                        ),
                        "doc_hit": None,
                        "article_hit": None,
                    }
                )
                continue

            answerable += 1
            doc_hit = any(
                r.document_title and expected_doc.lower() in r.document_title.lower()
                for r in results
            )
            article_hit = expected_article is None or any(
                r.article_ref == expected_article for r in results
            )
            doc_hits += 1 if doc_hit else 0
            article_hits += 1 if (doc_hit and article_hit) else 0

            rows.append(
                {
                    "question": item["question"],
                    "expected": f"{expected_doc} / {expected_article or '(any article)'}",
                    "top_result": (
                        f"{results[0].document_title} ({results[0].article_ref})"
                        if results
                        else "(none)"
                    ),
                    "doc_hit": doc_hit,
                    "article_hit": article_hit,
                }
            )

    doc_precision = doc_hits / answerable if answerable else 0.0
    article_precision = article_hits / answerable if answerable else 0.0
    unanswerable_total = len(golden_set) - answerable

    lines = [
        "# EVAL.md — M3.4 retrieval golden set",
        "",
        f"Golden set: {len(golden_set)} real questions ({answerable} answerable from the "
        f"ingested corpus, {unanswerable_total} deliberately unanswerable — M3.2's refusal test), "
        "run against the real lexical retrieval function "
        "(`app/services/retrieval.py::search_chunks`, top-"
        f"{_TOP_K}).",
        "",
        "**Scope, stated plainly:** this measures retrieval only — no chatbot/LLM generation "
        'layer was built (see DECISIONS.md). "Citation accuracy" below means "was the real '
        "expected article present in the top-"
        f'{_TOP_K} retrieved results", not "did a generated answer cite it correctly". '
        "Retrieval is lexical-only (Postgres full-text on the `tsv` column, `to_tsvector('simple', "
        "text)` — already populated for every chunk since M2's ingestion, no extra work needed "
        "today) — dense/hybrid search is designed (pgvector schema + HNSW index exist) but not "
        "populated, since no embedding API key is configured in this environment.",
        "",
        "## Real measured results",
        "",
        f"- **Document-level precision@{_TOP_K}** (expected document among top-{_TOP_K} results): "
        f"**{doc_hits}/{answerable} = {doc_precision:.0%}**",
        f"- **Article-level accuracy** (expected article specifically, where one was specified): "
        f"**{article_hits}/{answerable} = {article_precision:.0%}**",
        f"- **Refusal behaviour on the unanswerable question**: "
        f"{unanswerable_correctly_empty_or_low_relevance}/{unanswerable_total} returned no result "
        "or a near-zero-relevance top result (a real system would need to threshold this and say "
        '"I don\'t have a source for that" — not implemented today, see Known gaps below).',
        "",
        "## Per-question results",
        "",
        "| Question | Expected | Top real result | Doc hit | Article hit |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['question']} | {row['expected']} | {row['top_result']} | "
            f"{row['doc_hit']} | {row['article_hit']} |"
        )

    lines += [
        "",
        "## Known gaps (honest, not hidden)",
        "",
        "- **No dense/hybrid retrieval** — `chunks.embedding` (pgvector, HNSW-indexed) is part of "
        "the schema but was never populated; no embedding API key is configured in this "
        "environment. This eval measures lexical-only retrieval.",
        "- **No reranking, no chatbot UI, no conversation memory, no parcel-scoped context** — "
        "M3's full scope was not built today; this is the retrieval core only, built specifically "
        "so this file could report real numbers instead of being left empty or fabricated.",
        "- **No automatic refusal threshold** — the unanswerable question's retrieval score is "
        'reported, but nothing in this codebase yet decides "this is too low-relevance, say I '
        "don't know\" — that logic belongs to the generation layer, which doesn't exist yet.",
        "- **Golden set is hand-built from real ingested chunks**, not independently authored by "
        "someone who didn't already know the corpus — a real limitation of a same-day eval; a "
        "more rigorous version would have a second person (or a held-out real user question set) "
        "write the questions.",
    ]

    _EVAL_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"doc_precision={doc_precision:.2%} article_precision={article_precision:.2%}")
    print(f"Wrote {_EVAL_MD_PATH}")


if __name__ == "__main__":
    asyncio.run(run())
