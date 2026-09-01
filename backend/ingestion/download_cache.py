"""Cache-aware download helper shared by the M1 ingestion scripts.

M2.1 requires rate-limiting and a descriptive User-Agent for the real crawler.
Full incremental fetch (ETag / Last-Modified / content hash, tracked via the
`sources` table) belongs to that M2 pipeline. This is a smaller, honest scope
for now: skip re-downloading a file already cached locally. Good enough for
weekly-updated bulk files we fetch by hand today; M2 replaces this outright.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import structlog

from ingestion.config import CACHE_DIR, USER_AGENT

logger = structlog.get_logger(__name__)

_MIN_INTERVAL_S = 1.0
_last_request_at: float = 0.0


def download_cached(url: str, filename: str) -> Path:
    """Download `url` to CACHE_DIR/filename, reusing it if already present."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / filename
    if dest.exists():
        logger.info("download.cache_hit", url=url, path=str(dest))
        return dest

    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)

    logger.info("download.fetch", url=url)
    tmp = dest.with_name(dest.name + ".part")
    with httpx.stream(
        "GET", url, headers={"User-Agent": USER_AGENT}, timeout=180, follow_redirects=True
    ) as response:
        response.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)
    tmp.rename(dest)
    _last_request_at = time.monotonic()
    logger.info("download.complete", url=url, path=str(dest), bytes=dest.stat().st_size)
    return dest
