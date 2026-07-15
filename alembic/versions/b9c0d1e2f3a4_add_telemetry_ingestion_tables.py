"""feat: add telemetry ingestion tables (batch API, queue, normalized events, rollups)

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-07-15

Telemetry ingestion MVP: telemetry_events_raw is the DB-backed ingest queue and
immutable raw-payload archive (dedup gate: unique org+event_id);
telemetry_events is the normalized product event table (idempotent worker
writes via the same unique constraint); agent_metrics_daily is the precomputed
per-agent daily rollup (recomputed absolutely, never incremented).
"""
from alembic import op
import sqlalchemy as sa

revision = 'b9c0d1e2f3a4'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded per table: create_all() may already have built these (it runs
    # before Alembic on startup); re-creating would wedge the migration chain.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('telemetry_events_raw'):
        _create_raw()
    if not inspector.has_table('telemetry_events'):
        _create_events()
    if not inspector.has_table('agent_metrics_daily'):
        _create_metrics()


def _create_raw() -> None:
    op.create_table(
        'telemetry_events_raw',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('event_id', sa.String(64), nullable=False),
        sa.Column('api_key_id', sa.Integer(), nullable=True),
        sa.Column('raw_payload', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('error', sa.String(512), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'event_id', name='uq_telemetry_raw_org_event'),
    )
    op.create_index('ix_telemetry_events_raw_id', 'telemetry_events_raw', ['id'])
    op.create_index('ix_telemetry_events_raw_organization_id', 'telemetry_events_raw', ['organization_id'])
    op.create_index('ix_telemetry_raw_status_id', 'telemetry_events_raw', ['status', 'id'])
    op.create_index('ix_telemetry_raw_org_received', 'telemetry_events_raw', ['organization_id', 'received_at'])


def _create_events() -> None:
    op.create_table(
        'telemetry_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('event_id', sa.String(64), nullable=False),
        sa.Column('raw_id', sa.Integer(), nullable=True),
        sa.Column('api_key_id', sa.Integer(), nullable=True),
        sa.Column('agent_id', sa.String(256), nullable=False),
        sa.Column('asset_key', sa.String(64), nullable=True),
        sa.Column('agent_name', sa.String(256), nullable=True),
        sa.Column('team', sa.String(128), nullable=True),
        sa.Column('environment', sa.String(64), nullable=True),
        sa.Column('owner', sa.String(256), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('span_id', sa.String(32), nullable=True),
        sa.Column('parent_span_id', sa.String(32), nullable=True),
        sa.Column('provider', sa.String(128), nullable=True),
        sa.Column('model', sa.String(255), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('cost_estimated', sa.Boolean(), nullable=False),
        sa.Column('latency_ms', sa.Float(), nullable=True),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('error_message', sa.String(512), nullable=True),
        sa.Column('tool_name', sa.String(255), nullable=True),
        sa.Column('action_name', sa.String(255), nullable=True),
        sa.Column('risk_score', sa.Integer(), nullable=False),
        sa.Column('risk_reasons', sa.Text(), nullable=True),
        sa.Column('policy_action', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'event_id', name='uq_telemetry_events_org_event'),
    )
    op.create_index('ix_telemetry_events_id', 'telemetry_events', ['id'])
    op.create_index('ix_telemetry_events_organization_id', 'telemetry_events', ['organization_id'])
    op.create_index('ix_telemetry_events_asset_key', 'telemetry_events', ['asset_key'])
    op.create_index('ix_telemetry_events_timestamp', 'telemetry_events', ['timestamp'])
    op.create_index('ix_telemetry_events_trace_id', 'telemetry_events', ['trace_id'])
    op.create_index('ix_telemetry_events_org_agent_ts', 'telemetry_events',
                    ['organization_id', 'agent_id', 'timestamp'])
    op.create_index('ix_telemetry_events_org_asset_ts', 'telemetry_events',
                    ['organization_id', 'asset_key', 'timestamp'])
    op.create_index('ix_telemetry_events_org_ts', 'telemetry_events', ['organization_id', 'timestamp'])
    op.create_index('ix_telemetry_events_org_risk', 'telemetry_events', ['organization_id', 'risk_score'])


def _create_metrics() -> None:
    op.create_table(
        'agent_metrics_daily',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('agent_id', sa.String(256), nullable=False),
        sa.Column('asset_key', sa.String(64), nullable=True),
        sa.Column('agent_name', sa.String(256), nullable=True),
        sa.Column('team', sa.String(128), nullable=True),
        sa.Column('environment', sa.String(64), nullable=True),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('events_count', sa.Integer(), nullable=False),
        sa.Column('error_count', sa.Integer(), nullable=False),
        sa.Column('blocked_count', sa.Integer(), nullable=False),
        sa.Column('policy_violations', sa.Integer(), nullable=False),
        sa.Column('high_risk_events', sa.Integer(), nullable=False),
        sa.Column('total_input_tokens', sa.Integer(), nullable=False),
        sa.Column('total_output_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('total_cost_usd', sa.Float(), nullable=False),
        sa.Column('avg_latency_ms', sa.Float(), nullable=True),
        sa.Column('max_latency_ms', sa.Float(), nullable=True),
        sa.Column('avg_risk_score', sa.Float(), nullable=True),
        sa.Column('max_risk_score', sa.Integer(), nullable=False),
        sa.Column('models_json', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'agent_id', 'day', name='uq_agent_metrics_org_agent_day'),
    )
    op.create_index('ix_agent_metrics_daily_id', 'agent_metrics_daily', ['id'])
    op.create_index('ix_agent_metrics_daily_organization_id', 'agent_metrics_daily', ['organization_id'])
    op.create_index('ix_agent_metrics_daily_asset_key', 'agent_metrics_daily', ['asset_key'])
    op.create_index('ix_agent_metrics_org_day', 'agent_metrics_daily', ['organization_id', 'day'])
    op.create_index('ix_agent_metrics_org_team_day', 'agent_metrics_daily', ['organization_id', 'team', 'day'])


def downgrade() -> None:
    op.drop_table('agent_metrics_daily')
    op.drop_table('telemetry_events')
    op.drop_table('telemetry_events_raw')
