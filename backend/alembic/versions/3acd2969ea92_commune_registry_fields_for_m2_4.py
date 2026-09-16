"""commune registry fields for M2.4

Revision ID: 3acd2969ea92
Revises: 74fe4bc43e92
Create Date: 2026-09-15 20:05:59.072355
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3acd2969ea92"
down_revision: str | None = "74fe4bc43e92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("communes", sa.Column("website_url", sa.Text(), nullable=True))
    op.add_column("communes", sa.Column("geoportal_slug", sa.Text(), nullable=True))
    op.add_column("communes", sa.Column("population", sa.Integer(), nullable=True))
    op.add_column("communes", sa.Column("cms_hosting_provider", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("communes", "cms_hosting_provider")
    op.drop_column("communes", "population")
    op.drop_column("communes", "geoportal_slug")
    op.drop_column("communes", "website_url")
