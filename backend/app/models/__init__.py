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
from app.models.chat import ChatMessage
from app.models.overlays import ParcelOverlayResult
from app.models.pag import PagZone, PapNqZone, PapQeZone
from app.models.provenance import Chunk, Document, LegislationVersion, Source
from app.models.slope import ParcelSlopeResult

__all__ = [
    "Address",
    "Building",
    "BuildingNature",
    "CadastralCommune",
    "CadastralSection",
    "ChatMessage",
    "Chunk",
    "Commune",
    "Document",
    "LegislationVersion",
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
