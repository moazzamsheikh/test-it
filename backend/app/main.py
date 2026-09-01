"""FastAPI app entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="Alix — Luxembourg Parcel Intelligence Platform")
# Dev-only: the Next.js frontend runs on a different origin (localhost:3000).
# Not required by the assessment (auth/multi-tenancy are explicitly out of
# scope), scoped to localhost rather than "*" anyway as a matter of habit.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(v1_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
