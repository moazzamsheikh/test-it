"""document_id on parcel_overlay_results for M2 ZPIN dynamic linking

Revision ID: 74fe4bc43e92
Revises: b4054cb7ca57
Create Date: 2026-09-08 01:19:13.171595
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "74fe4bc43e92"
down_revision: str | None = "b4054cb7ca57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "parcel_overlay_results_document_id_fkey"


def upgrade() -> None:
    op.add_column("parcel_overlay_results", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        _FK_NAME,
        "parcel_overlay_results",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_FK_NAME, "parcel_overlay_results", type_="foreignkey")
    op.drop_column("parcel_overlay_results", "document_id")
