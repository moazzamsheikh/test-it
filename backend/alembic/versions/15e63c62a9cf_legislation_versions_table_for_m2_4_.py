"""legislation versions table for M2.4 amendment-chain bonus

Revision ID: 15e63c62a9cf
Revises: 3acd2969ea92
Create Date: 2026-09-15 21:33:45.911717
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "15e63c62a9cf"
down_revision: str | None = "3acd2969ea92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legislation_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("work_eli", sa.Text(), nullable=False),
        sa.Column("version_eli", sa.Text(), nullable=False),
        sa.Column("expression_url", sa.Text(), nullable=False),
        sa.Column("date_applicability", sa.Date(), nullable=False),
        sa.Column("date_end_applicability", sa.Date(), nullable=True),
        sa.Column("in_force_status", sa.String(length=50), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_eli", name="uq_legislation_versions_version_eli"),
    )
    op.create_index(
        "ix_legislation_versions_work_date",
        "legislation_versions",
        ["work_eli", "date_applicability"],
        unique=False,
    )
    op.create_index(
        op.f("ix_legislation_versions_work_eli"), "legislation_versions", ["work_eli"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_legislation_versions_work_eli"), table_name="legislation_versions")
    op.drop_index("ix_legislation_versions_work_date", table_name="legislation_versions")
    op.drop_table("legislation_versions")
