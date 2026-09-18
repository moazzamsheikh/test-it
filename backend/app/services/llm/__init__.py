"""LLM provider factory — the one place `settings.llm_provider`/
`settings.gemini_api_key` is read to pick a concrete implementation.
Everything else in the app (chatbot.py, reranking.py) depends only on the
`LLMProvider` Protocol in `base.py`, never on `GeminiProvider` or
`google.genai` directly — that's the actual "swap models without touching
business logic" requirement, not just an aspiration in a comment."""

from __future__ import annotations

import structlog

from app.core.config import settings
from app.services.llm.base import ChatTurn, LLMProvider, SourcePassage
from app.services.llm.extractive import ExtractiveProvider
from app.services.llm.gemini import GeminiProvider

logger = structlog.get_logger(__name__)

__all__ = ["ChatTurn", "LLMProvider", "SourcePassage", "get_llm_provider"]

_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider

    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        _provider = GeminiProvider()
    else:
        logger.warning(
            "llm.no_provider_configured",
            llm_provider=settings.llm_provider,
            has_key=bool(settings.gemini_api_key),
        )
        _provider = ExtractiveProvider()
    return _provider
