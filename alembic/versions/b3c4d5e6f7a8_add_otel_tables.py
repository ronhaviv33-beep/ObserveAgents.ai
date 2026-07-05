"""feat: add otel_spans and provenance_events tables for OTel trace ingestion

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-01

otel_spans stores privacy-scrubbed OTLP span records (no raw content).
provenance_events stores derived semantic events (llm_call, tool_call, etc.).
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7a8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded per table: create_all() may already have built these (it runs
    # before Alembic on startup); re-creating would wedge the migration chain.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('otel_spans'):
        _create_otel_spans()
    if not inspector.has_table('provenance_events'):
        _create_provenance_events()


def _create_otel_spans() -> None:
    op.create_table(
        'otel_spans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('trace_id', sa.String(64), nullable=False),
        sa.Column('span_id', sa.String(32), nullable=False),
        sa.Column('parent_span_id', sa.String(32), nullable=True),
        sa.Column('service_name', sa.String(255), nullable=True),
        sa.Column('span_name', sa.String(255), nullable=False),
        sa.Column('span_kind', sa.Integer(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('status_code', sa.String(32), nullable=True),
        sa.Column('status_message', sa.String(512), nullable=True),
        sa.Column('attributes_json', sa.Text(), nullable=True),
        sa.Column('resource_attributes_json', sa.Text(), nullable=True),
        sa.Column('events_json', sa.Text(), nullable=True),
        sa.Column('links_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'trace_id', 'span_id', name='uq_otel_spans_org_trace_span'),
    )
    op.create_index('ix_otel_spans_id',              'otel_spans', ['id'])
    op.create_index('ix_otel_spans_organization_id', 'otel_spans', ['organization_id'])
    op.create_index('ix_otel_spans_trace_id',        'otel_spans', ['trace_id'])
    op.create_index('ix_otel_spans_service_name',    'otel_spans', ['service_name'])


def _create_provenance_events() -> None:
    op.create_table(
        'provenance_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('trace_id', sa.String(64), nullable=False),
        sa.Column('span_id', sa.String(32), nullable=True),
        sa.Column('parent_span_id', sa.String(32), nullable=True),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('source_type', sa.String(64), nullable=True),
        sa.Column('source_name', sa.String(255), nullable=True),
        sa.Column('target_type', sa.String(64), nullable=True),
        sa.Column('target_name', sa.String(255), nullable=True),
        sa.Column('relation_type', sa.String(64), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attributes_json', sa.Text(), nullable=True),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('content_redacted', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_provenance_events_id',              'provenance_events', ['id'])
    op.create_index('ix_provenance_events_organization_id', 'provenance_events', ['organization_id'])
    op.create_index('ix_provenance_events_trace_id',        'provenance_events', ['trace_id'])
    op.create_index('ix_provenance_events_span_id',         'provenance_events', ['span_id'])
    op.create_index('ix_provenance_events_event_type',      'provenance_events', ['event_type'])
    op.create_index('ix_provenance_events_target_type',     'provenance_events', ['target_type'])
    op.create_index('ix_provenance_events_target_name',     'provenance_events', ['target_name'])
    op.create_index('ix_provenance_events_timestamp',       'provenance_events', ['timestamp'])


def downgrade() -> None:
    op.drop_index('ix_provenance_events_timestamp',       table_name='provenance_events')
    op.drop_index('ix_provenance_events_target_name',     table_name='provenance_events')
    op.drop_index('ix_provenance_events_target_type',     table_name='provenance_events')
    op.drop_index('ix_provenance_events_event_type',      table_name='provenance_events')
    op.drop_index('ix_provenance_events_span_id',         table_name='provenance_events')
    op.drop_index('ix_provenance_events_trace_id',        table_name='provenance_events')
    op.drop_index('ix_provenance_events_organization_id', table_name='provenance_events')
    op.drop_index('ix_provenance_events_id',              table_name='provenance_events')
    op.drop_table('provenance_events')

    op.drop_index('ix_otel_spans_service_name',    table_name='otel_spans')
    op.drop_index('ix_otel_spans_trace_id',        table_name='otel_spans')
    op.drop_index('ix_otel_spans_organization_id', table_name='otel_spans')
    op.drop_index('ix_otel_spans_id',              table_name='otel_spans')
    op.drop_table('otel_spans')
