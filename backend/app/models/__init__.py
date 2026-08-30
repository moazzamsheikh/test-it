"""Import all ORM models so they register on Base.metadata for Alembic."""

from app.models.cadastre import (
    Address,
    Building,
    BuildingNature,
    CadastralCommune,
    CadastralSection,
    Commune,
    Parcel,
    ParcelBuilding,
    ParcelNature,
)
from app.models.provenance import Chunk, Document, Source

__all__ = [
    "Address",
    "Building",
    "BuildingNature",
    "CadastralCommune",
    "CadastralSection",
    "Chunk",
    "Commune",
    "Document",
    "Parcel",
    "ParcelBuilding",
    "ParcelNature",
    "Source",
]
