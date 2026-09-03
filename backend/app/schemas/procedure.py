"""M5 procedure response schema — a structured, citation-backed display of
ONE real ingested procedure document (see DECISIONS.md: this is honestly
scoped as a document display, not a chatbot/semantic search — that's M3)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ProcedureSection(BaseModel):
    heading: str
    text: str


class LegalReference(BaseModel):
    label: str
    url: str


class ProcedureDetail(BaseModel):
    title: str
    source_url: str
    publisher: str
    document_date: date | None
    sections: list[ProcedureSection]
    legal_references: list[LegalReference]
