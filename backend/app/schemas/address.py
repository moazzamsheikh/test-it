"""Pydantic response models for the address search API (M1.2)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class AddressSearchResult(BaseModel):
    id: uuid.UUID
    street_name: str
    house_number: str
    locality: str | None
    postal_code: str | None
    admin_commune_code: str | None
    admin_commune_name: str | None
    parcel_cadastral_id: str | None
    lat: float
    lon: float
    score: float
