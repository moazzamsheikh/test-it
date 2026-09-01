"""FastAPI app entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="Alix — Luxembourg Parcel Intelligence Platform")
app.include_router(v1_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
