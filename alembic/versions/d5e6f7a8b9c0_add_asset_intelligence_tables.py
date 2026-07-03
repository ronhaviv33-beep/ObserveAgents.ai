"""feat: add asset_capabilities and asset_findings tables

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-03

asset_capabilities normalizes capabilities derived from OTel evidence:
one row per (org, asset_key, capability_type, capability_name, source).

asset_findings stores general findings derived from AI asset activity
across security, performance, operations, dependency, inventory, and
governance dimensions.

No unique indexes on either table — application-level dedup is used.
"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'asset_capabilities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('asset_registry.id'), nullable=True),
        sa.Column('asset_key', sa.String(64), nullable=True),
        sa.Column('capability_type', sa.String(64), nullable=False),
        sa.Column('capability_name', sa.String(255), nullable=False),
        sa.Column('source', sa.String(64), nullable=False),
        sa.Column('evidence_json', sa.Text(), nullable=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_asset_capabilities_id',              'asset_capabilities', ['id'])
    op.create_index('ix_asset_capabilities_organization_id', 'asset_capabilities', ['organization_id'])
    op.create_index('ix_asset_capabilities_asset_id',        'asset_capabilities', ['asset_id'])
    op.create_index('ix_asset_capabilities_asset_key',       'asset_capabilities', ['asset_key'])
    op.create_index('ix_asset_capabilities_capability_type', 'asset_capabilities', ['capability_type'])
    op.create_index('ix_asset_capabilities_capability_name', 'asset_capabilities', ['capability_name'])
    op.create_index('ix_asset_capabilities_source',          'asset_capabilities', ['source'])
    op.create_index('ix_asset_capabilities_last_seen',       'asset_capabilities', ['last_seen'])

    op.create_table(
        'asset_findings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('asset_registry.id'), nullable=True),
        sa.Column('asset_key', sa.String(64), nullable=True),
        sa.Column('category', sa.String(32), nullable=False),
        sa.Column('finding_type', sa.String(64), nullable=False),
        sa.Column('severity', sa.String(16), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('evidence_json', sa.Text(), nullable=True),
        sa.Column('source', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='open'),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_asset_findings_id',              'asset_findings', ['id'])
    op.create_index('ix_asset_findings_organization_id', 'asset_findings', ['organization_id'])
    op.create_index('ix_asset_findings_asset_id',        'asset_findings', ['asset_id'])
    op.create_index('ix_asset_findings_asset_key',       'asset_findings', ['asset_key'])
    op.create_index('ix_asset_findings_category',        'asset_findings', ['category'])
    op.create_index('ix_asset_findings_finding_type',    'asset_findings', ['finding_type'])
    op.create_index('ix_asset_findings_severity',        'asset_findings', ['severity'])
    op.create_index('ix_asset_findings_status',          'asset_findings', ['status'])
    op.create_index('ix_asset_findings_source',          'asset_findings', ['source'])
    op.create_index('ix_asset_findings_last_seen',       'asset_findings', ['last_seen'])


def downgrade() -> None:
    op.drop_index('ix_asset_findings_last_seen',       table_name='asset_findings')
    op.drop_index('ix_asset_findings_source',          table_name='asset_findings')
    op.drop_index('ix_asset_findings_status',          table_name='asset_findings')
    op.drop_index('ix_asset_findings_severity',        table_name='asset_findings')
    op.drop_index('ix_asset_findings_finding_type',    table_name='asset_findings')
    op.drop_index('ix_asset_findings_category',        table_name='asset_findings')
    op.drop_index('ix_asset_findings_asset_key',       table_name='asset_findings')
    op.drop_index('ix_asset_findings_asset_id',        table_name='asset_findings')
    op.drop_index('ix_asset_findings_organization_id', table_name='asset_findings')
    op.drop_index('ix_asset_findings_id',              table_name='asset_findings')
    op.drop_table('asset_findings')

    op.drop_index('ix_asset_capabilities_last_seen',       table_name='asset_capabilities')
    op.drop_index('ix_asset_capabilities_source',          table_name='asset_capabilities')
    op.drop_index('ix_asset_capabilities_capability_name', table_name='asset_capabilities')
    op.drop_index('ix_asset_capabilities_capability_type', table_name='asset_capabilities')
    op.drop_index('ix_asset_capabilities_asset_key',       table_name='asset_capabilities')
    op.drop_index('ix_asset_capabilities_asset_id',        table_name='asset_capabilities')
    op.drop_index('ix_asset_capabilities_organization_id', table_name='asset_capabilities')
    op.drop_index('ix_asset_capabilities_id',              table_name='asset_capabilities')
    op.drop_table('asset_capabilities')
