"""perf: add missing indexes on telemetry and asset_registry hot-query columns

Revision ID: a1b2c3d4e5f6
Revises: 7b3e2f1a4c89
Create Date: 2026-06-24

Without these indexes every time-range query on telemetry is a full-table scan.
The composite (organization_id, timestamp) index is the single most important one
because almost every query filters on both columns.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '7b3e2f1a4c89'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded per index: on DBs built by create_all() the single-column ix_
    # names already exist, and on very old DBs some columns may be missing —
    # either case would otherwise wedge the migration chain.
    inspector = sa.inspect(op.get_bind())

    def _create_index(name: str, table: str, cols: list[str]) -> None:
        if not inspector.has_table(table):
            return
        if name in {ix["name"] for ix in inspector.get_indexes(table)}:
            return
        if not set(cols) <= {c["name"] for c in inspector.get_columns(table)}:
            return
        op.create_index(name, table, cols)

    # ── telemetry: most-queried columns ──────────────────────────────────────────
    # Composite (organization_id, timestamp) — hits the WHERE clause on every
    # time-range query: assets, cost, trends, security alerts, budget spend.
    _create_index('ix_telemetry_org_timestamp', 'telemetry', ['organization_id', 'timestamp'])
    # Composite (organization_id, is_demo, timestamp) — every query also filters
    # is_demo; the three-column index avoids a post-index scan on is_demo.
    _create_index('ix_telemetry_org_demo_timestamp', 'telemetry', ['organization_id', 'is_demo', 'timestamp'])
    # Single-column indexes for filter + GROUP BY selectivity
    _create_index('ix_telemetry_timestamp', 'telemetry', ['timestamp'])
    _create_index('ix_telemetry_agent',     'telemetry', ['agent'])
    _create_index('ix_telemetry_team',      'telemetry', ['team'])
    _create_index('ix_telemetry_model',     'telemetry', ['model'])
    _create_index('ix_telemetry_blocked',   'telemetry', ['blocked'])
    _create_index('ix_telemetry_sensitive', 'telemetry', ['sensitive'])
    _create_index('ix_telemetry_is_demo',   'telemetry', ['is_demo'])

    # ── asset_registry: status filtering ─────────────────────────────────────────
    _create_index('ix_asset_registry_status',     'asset_registry', ['status'])
    _create_index('ix_asset_registry_asset_type', 'asset_registry', ['asset_type'])
    _create_index('ix_asset_registry_org_status', 'asset_registry', ['organization_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_asset_registry_org_status',   table_name='asset_registry')
    op.drop_index('ix_asset_registry_asset_type',   table_name='asset_registry')
    op.drop_index('ix_asset_registry_status',       table_name='asset_registry')
    op.drop_index('ix_telemetry_is_demo',           table_name='telemetry')
    op.drop_index('ix_telemetry_sensitive',         table_name='telemetry')
    op.drop_index('ix_telemetry_blocked',           table_name='telemetry')
    op.drop_index('ix_telemetry_model',             table_name='telemetry')
    op.drop_index('ix_telemetry_team',              table_name='telemetry')
    op.drop_index('ix_telemetry_agent',             table_name='telemetry')
    op.drop_index('ix_telemetry_timestamp',         table_name='telemetry')
    op.drop_index('ix_telemetry_org_demo_timestamp', table_name='telemetry')
    op.drop_index('ix_telemetry_org_timestamp',     table_name='telemetry')
