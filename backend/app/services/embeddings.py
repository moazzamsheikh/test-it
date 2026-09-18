"""M3.1 — dense embeddings for hybrid retrieval.

Originally planned as a self-hosted multilingual model (BGE-m3/e5-large
class — see the 1024-d `Chunk.embedding` column pinned in
`app/models/provenance.py::EMBEDDING_DIM`), for cost (compute, not
per-token) and no external dependency at query time. Pivoted after
verifying, not assuming, that this environment's Python (3.14) has no
`torch`/`onnxruntime` wheels available from PyPI — both `sentence-transformers`
and `fastembed` fail to install here (see DECISIONS.md for the exact pip
errors). Google's `gemini-embedding-001` supports a configurable
`output_dimensionality`, so 1024-d was kept and the schema/migration are
unchanged — only the model source moved from self-hosted to an API call.

Cost, calculated not guessed (debrief Q1): gemini-embedding-001 is priced
per input token; our whole 8-commune + national-legislation corpus (1,689
chunks, ~370K characters after the truncation below, ~100K tokens) costs a
small fraction of a cent to embed from scratch. Scaling to 102 communes
(~13x the commune-chunk volume, per SCALING.md) stays well under $1.

Multilingual strategy (M3.1's explicit "handle deliberately" requirement):
gemini-embedding-001 is trained across 100+ languages including French and
German. Luxembourgish (LB) is not a language it was explicitly trained on;
LB queries are expected to land in embedding space close to their German
cognates (LB is West-Germanic, heavy German vocabulary overlap) rather than
matching with the same fidelity as FR/DE/EN — a real, disclosed limitation,
not a claim of full LB support. Full LB coverage would need a
language-specific model or a translation pre-pass, out of scope here (a
disclosed gap, see DECISIONS.md and the +2 trilingual bonus discussion).
"""

from __future__ import annotations

import asyncio
from typing import Literal

import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = structlog.get_logger(__name__)

# gemini-embedding-001's documented input limit is 2048 tokens; anything
# beyond is silently truncated server-side rather than rejected (verified
# live: a 20,000-token input returns 200 OK, not an error). Truncating to
# ~2000 tokens' worth of characters ourselves avoids paying for/uploading
# tokens the API would drop anyway. At ~4 chars/token for French/German
# legal prose, that's roughly 8,000 characters — real effect: for the ~94
# oversized whole-document PAG/bylaw chunks (see retrieval.py's own
# docstring on this pre-existing M2 gap), only the *beginning* of the
# document is represented in the dense vector. Lexical full-text search
# (which scans the whole chunk) is the compensating signal for exactly
# these chunks — the brief's own M3.1 rationale for hybrid search, borne
# out concretely in this corpus rather than just asserted.
_MAX_EMBED_CHARS = 8000

# Gemini batches multiple `contents` into one request (verified live, order
# preserved) — real, not an assumption. Kept well under any request-size
# limit while still cutting the number of HTTP round-trips for the ~1,700
# chunks in this corpus by ~50x versus one-at-a-time.
_BATCH_SIZE = 32

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set — required for dense embeddings. "
                "Retrieval falls back to lexical-only if this is never called."
            )
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _is_rate_limit_error(exc: BaseException) -> bool:
    return isinstance(exc, genai_errors.ClientError) and exc.code == 429


def _embed_batch_uncached(batch: list[str], task_type: TaskType) -> list[list[float]]:
    """No retry here — callers decide how patient to be (see the two
    wrappers below), since that differs sharply between an offline backfill
    and a live request."""
    client = _get_client()
    try:
        response = client.models.embed_content(
            model=settings.embedding_model_name,
            # google-genai's overloaded `contents` type is invariant on
            # `list[str]` vs. its broader `list[str | Image | ...]` union,
            # so mypy strict rejects a plain `list[str]` here even though
            # it's exactly what the SDK's own examples pass and what was
            # verified live (batch embedding calls, see DECISIONS.md).
            contents=batch,  # type: ignore[arg-type]
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dim,
                task_type=task_type,
            ),
        )
    except genai_errors.ClientError as exc:
        if exc.code == 429:
            logger.warning("embeddings.rate_limited", batch_size=len(batch))
        raise
    return [list(e.values or []) for e in (response.embeddings or [])]


# The free-tier embedding quota is real and tight; whether a given stall is
# a short per-minute throttle or a longer-window cap varies by how much of
# it prior calls in the same run already used (verified live: recovers
# within ~20s in isolation, but the same spacing kept failing for several
# minutes right after a heavier burst). A handful of retries here catches
# the short-throttle case cheaply; `ingestion/embed_chunks.py` is the outer
# safety net for the rest — it skips a batch that's still failing after
# this budget rather than burning many more minutes on one batch (M2.1's
# "a failing item is logged and skipped, never aborts the run", applied to
# an API-based step instead of a web crawl), and picks it up again on a
# later `make embed` since only `embedding IS NULL` chunks are selected.
# Deliberately NOT used for the live query path below — a multi-minute
# retry budget is fine for a one-off offline backfill, not for a chat
# request a user is waiting on.
_patient_retry = retry(
    retry=retry_if_exception(_is_rate_limit_error),
    wait=wait_exponential(multiplier=15, min=15, max=60),
    stop=stop_after_attempt(4),
    reraise=True,
)(_embed_batch_uncached)

# A live chat request degrades to lexical-only the moment dense embedding
# fails (app/services/retrieval.py::hybrid_search) — that's the right
# response to this account's real quota constraints, not a longer wait.
# One short retry only catches a request that lands exactly on a boundary;
# it must not turn into the multi-minute budget above and make a user
# stare at a spinner.
_fast_retry = retry(
    retry=retry_if_exception(_is_rate_limit_error),
    wait=wait_exponential(multiplier=3, min=3, max=6),
    stop=stop_after_attempt(2),
    reraise=True,
)(_embed_batch_uncached)


def embed_texts_sync(texts: list[str], *, task_type: TaskType) -> list[list[float]]:
    """Blocking version — used by `ingestion/embed_chunks.py`, which (like
    every other ingestion script in this project) is a plain synchronous
    script, not an asyncio program. Uses the patient retry budget."""
    if not texts:
        return []

    truncated = [t[:_MAX_EMBED_CHARS] for t in texts]

    results: list[list[float]] = []
    for i in range(0, len(truncated), _BATCH_SIZE):
        batch = truncated[i : i + _BATCH_SIZE]
        results.extend(_patient_retry(batch, task_type))

    return results


async def embed_texts(texts: list[str], *, task_type: TaskType) -> list[list[float]]:
    """Async wrapper for the FastAPI request path — runs the blocking SDK
    call in a thread (google-genai's client has no native asyncio surface)
    so a live chat request doesn't block the event loop. Uses the fast-fail
    retry budget (see `_fast_retry`)."""
    if not texts:
        return []
    truncated = [t[:_MAX_EMBED_CHARS] for t in texts]
    return await asyncio.to_thread(_fast_retry, truncated, task_type)


async def embed_query(text: str) -> list[float]:
    """RETRIEVAL_QUERY and RETRIEVAL_DOCUMENT are asymmetric task types in
    this model — using the wrong one for a query measurably hurts cosine
    similarity against document embeddings (Google's own documented
    behaviour for this model family). Never reuse this for indexing."""
    embeddings = await embed_texts([text], task_type="RETRIEVAL_QUERY")
    return embeddings[0]
