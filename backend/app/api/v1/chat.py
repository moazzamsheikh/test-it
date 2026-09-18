"""M3 — grounded, parcel-scoped chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chatbot import answer_question

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    return await answer_question(
        session,
        session_id=request.session_id,
        message=request.message,
        cadastral_id=request.cadastral_id,
    )
