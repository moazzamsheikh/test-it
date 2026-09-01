from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.addresses import router as addresses_router
from app.api.v1.parcels import router as parcels_router

router = APIRouter(prefix="/api/v1")
router.include_router(addresses_router)
router.include_router(parcels_router)
