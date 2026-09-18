"""M3.1 — populate `chunks.embedding` for dense retrieval.

Not a `sources`/`documents`/`chunks` crawler like every other ingestion
script here — this derives a value from data already ingested, so there is
no new `Source` row. Idempotent the simple way: only chunks with
`embedding IS NULL` are processed, so a second run (e.g. after a fresh
`make ingest`) only pays for genuinely new chunks. Pass `--force` to
re-embed everything (e.g. after changing `embedding_model_name`).

Run with: make embed
"""

from __future__ import annotations

import argparse
import time

import httpx
import structlog
from google.genai import errors as genai_errors
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.models.provenance import Chunk
from app.services.embeddings import embed_texts_sync

logger = structlog.get_logger(__name__)

# One DB round-trip per batch, not per chunk — 1,689 real chunks means ~53
# batches at this size rather than 1,689 individual UPDATE statements.
_DB_BATCH_SIZE = 32


def embed_all(session: Session, *, force: bool) -> dict[str, int]:
    stmt = select(Chunk.id, Chunk.text)
    if not force:
        stmt = stmt.where(Chunk.embedding.is_(None))
    rows = session.execute(stmt).all()

    embedded = 0
    skipped = 0
    for i in range(0, len(rows), _DB_BATCH_SIZE):
        batch = rows[i : i + _DB_BATCH_SIZE]
        try:
            vectors = embed_texts_sync([r.text for r in batch], task_type="RETRIEVAL_DOCUMENT")
        except (genai_errors.ClientError, httpx.TransportError) as exc:
            # M2.1's own resilience rule ("a failing source is logged and
            # skipped, never aborts the run") applies just as much to this
            # API-based step as to a web crawl. Two real, live-encountered
            # failure modes, both non-fatal to the overall run: this
            # account's free-tier gemini-embedding-001 quota is tight enough
            # that a single run may not clear the whole backlog (ClientError
            # 429), and a plain transient network reset ("Connection reset
            # by peer", httpx.ConnectError — a TransportError subclass) that
            # crashed an earlier run outright since it isn't a ClientError
            # at all. Skipping this batch (still `embedding IS NULL`, so a
            # later `make embed` retries it) beats losing all progress made
            # so far to either one.
            logger.error(
                "ingest.embed_chunks.batch_failed_skipping",
                batch_start=i,
                batch_size=len(batch),
                error=str(exc)[:300],
            )
            skipped += len(batch)
            continue

        for row, vector in zip(batch, vectors, strict=True):
            session.execute(update(Chunk).where(Chunk.id == row.id).values(embedding=vector))
        session.commit()
        embedded += len(batch)
        logger.info("ingest.embed_chunks.batch", done=embedded, skipped=skipped, total=len(rows))
        # Real free-tier Gemini embedding quota is tight, per-minute, and
        # evidently stateful across a burst of prior failed requests, not
        # just a clean sliding window — verified live: 8s/13s spacing hit
        # sustained 429s, a 20s-spaced probe of 4 isolated calls ran clean,
        # but resuming this script at 20s spacing right after an earlier
        # 429 storm still failed for several more minutes. 30s plus the
        # generous retry-with-backoff in app/services/embeddings.py is a
        # deliberately patient choice for a one-off backfill, not a number
        # this needs to be fast at.
        time.sleep(30.0)

    return {"chunks_considered": len(rows), "chunks_embedded": embedded, "chunks_skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Re-embed every chunk, not just new ones."
    )
    args = parser.parse_args()

    configure_logging()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        result = embed_all(session, force=args.force)
    logger.info("ingest.embed_chunks.complete", **result)


if __name__ == "__main__":
    main()
