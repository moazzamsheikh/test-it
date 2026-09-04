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
from app.models.overlays import ParcelOverlayResult
from app.models.pag import PagZone, PapNqZone, PapQeZone
from app.models.provenance import Chunk, Document, Source
from app.models.slope import ParcelSlopeResult

__all__ = [
    "Address",
    "Building",
    "BuildingNature",
    "CadastralCommune",
    "CadastralSection",
    "Chunk",
    "Commune",
    "Document",
    "PagZone",
    "PapNqZone",
    "PapQeZone",
    "Parcel",
    "ParcelBuilding",
    "ParcelNature",
    "ParcelOverlayResult",
    "ParcelSlopeResult",
    "Source",
]
