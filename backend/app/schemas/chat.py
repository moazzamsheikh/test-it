"""M3 — chat request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)
    # Optional: the architect may not always have a parcel selected (e.g.
    # "what is a PAP QE?"). When set, retrieval scopes to that parcel's
    # commune + national legislation, and the answer surfaces M1/M2
    # geospatial facts alongside textual citations (M3.3).
    cadastral_id: str | None = None


class ChatCitation(BaseModel):
    ref_id: int
    document_title: str
    article_ref: str | None
    source_url: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation]
    refused: bool
    parcel_cadastral_id: str | None
