"""asset taxonomy v2 - asset_type and capabilities

Revision ID: 7b3e2f1a4c89
Revises: 4f2a8c1d9e03
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = '7b3e2f1a4c89'
down_revision = '4f2a8c1d9e03'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded: on DBs where create_all()/schema repair already added these
    # columns, re-adding would fail and wedge the whole migration chain.
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("asset_registry")}
    if "asset_type" not in existing:
        op.add_column("asset_registry", sa.Column("asset_type", sa.String(32), nullable=True, server_default="agent"))
    if "capabilities" not in existing:
        op.add_column("asset_registry", sa.Column("capabilities", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("asset_registry", "capabilities")
    op.drop_column("asset_registry", "asset_type")
