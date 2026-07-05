"""fix: add occurrence_count to asset_findings

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-05

One finding row now represents all matching spans in a derive run; this
column records how many occurrences the row stands for. Recomputed
absolutely on every intelligence run.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded: create_all()/ensure_model_columns() may already have added the
    # column (both run before Alembic on startup).
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('asset_findings'):
        return
    cols = {c['name'] for c in inspector.get_columns('asset_findings')}
    if 'occurrence_count' in cols:
        return
    op.add_column(
        'asset_findings',
        sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('asset_findings', 'occurrence_count')
