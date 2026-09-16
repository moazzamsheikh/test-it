"""graphic document links for PAP QE and NQ schema directeur maps

Revision ID: 246235b7d975
Revises: 15e63c62a9cf
Create Date: 2026-09-15 22:00:38.018054
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "246235b7d975"
down_revision: str | None = "15e63c62a9cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_QE_FK_NAME = "pap_qe_zones_graphic_document_id_fkey"
_NQ_FK_NAME = "pap_nq_zones_schema_directeur_graphic_document_id_fkey"


def upgrade() -> None:
    op.add_column("pap_qe_zones", sa.Column("graphic_document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        _QE_FK_NAME,
        "pap_qe_zones",
        "documents",
        ["graphic_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "pap_nq_zones", sa.Column("schema_directeur_graphic_document_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        _NQ_FK_NAME,
        "pap_nq_zones",
        "documents",
        ["schema_directeur_graphic_document_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_NQ_FK_NAME, "pap_nq_zones", type_="foreignkey")
    op.drop_column("pap_nq_zones", "schema_directeur_graphic_document_id")
    op.drop_constraint(_QE_FK_NAME, "pap_qe_zones", type_="foreignkey")
    op.drop_column("pap_qe_zones", "graphic_document_id")
