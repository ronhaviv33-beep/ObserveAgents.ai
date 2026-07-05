"""feat: add otel_assets evidence summary table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-02

otel_assets summarises OTel discovery evidence per (org, service, environment).
One row per unique identity; aggregates models/providers/tools/dependencies
seen across ingested spans. FK to asset_registry (canonical AI inventory).

No unique index: environment and agent_name are nullable; application-level
dedup is used instead (see app/otel_normalizer.upsert_otel_asset).
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded: create_all() may already have built this table (it runs before
    # Alembic on startup); re-creating it would wedge the migration chain.
    if sa.inspect(op.get_bind()).has_table('otel_assets'):
        return
    op.create_table(
        'otel_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('ai_asset_id', sa.Integer(), sa.ForeignKey('asset_registry.id'), nullable=True),
        sa.Column('service_name', sa.String(255), nullable=False),
        sa.Column('service_namespace', sa.String(255), nullable=True),
        sa.Column('service_instance_id', sa.String(255), nullable=True),
        sa.Column('environment', sa.String(64), nullable=True),
        sa.Column('agent_name', sa.String(255), nullable=True),
        sa.Column('models_json', sa.Text(), nullable=True),
        sa.Column('providers_json', sa.Text(), nullable=True),
        sa.Column('tools_json', sa.Text(), nullable=True),
        sa.Column('dependencies_json', sa.Text(), nullable=True),
        sa.Column('resource_attributes_json', sa.Text(), nullable=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('trace_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('span_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_otel_assets_id',              'otel_assets', ['id'])
    op.create_index('ix_otel_assets_organization_id', 'otel_assets', ['organization_id'])
    op.create_index('ix_otel_assets_ai_asset_id',     'otel_assets', ['ai_asset_id'])
    op.create_index('ix_otel_assets_service_name',    'otel_assets', ['service_name'])
    op.create_index('ix_otel_assets_agent_name',      'otel_assets', ['agent_name'])
    op.create_index('ix_otel_assets_environment',     'otel_assets', ['environment'])
    op.create_index('ix_otel_assets_last_seen',       'otel_assets', ['last_seen'])


def downgrade() -> None:
    op.drop_index('ix_otel_assets_last_seen',       table_name='otel_assets')
    op.drop_index('ix_otel_assets_environment',     table_name='otel_assets')
    op.drop_index('ix_otel_assets_agent_name',      table_name='otel_assets')
    op.drop_index('ix_otel_assets_service_name',    table_name='otel_assets')
    op.drop_index('ix_otel_assets_ai_asset_id',     table_name='otel_assets')
    op.drop_index('ix_otel_assets_organization_id', table_name='otel_assets')
    op.drop_index('ix_otel_assets_id',              table_name='otel_assets')
    op.drop_table('otel_assets')
